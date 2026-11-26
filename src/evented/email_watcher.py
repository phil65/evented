"""Email event source."""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any, Self

from evented.base import EventSource
from evented.event_data import EmailEventData
from evented.log import get_logger


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from types import TracebackType

    import aioimaplib

    from evented.event_data import EventData
    from evented_config import EmailConfig

logger = get_logger(__name__)


class EmailEventSource(EventSource):
    """Monitors email inbox for events."""

    def __init__(self, config: EmailConfig):
        self.config = config
        self._stop_event = asyncio.Event()
        self._client: aioimaplib.IMAP4_SSL | aioimaplib.IMAP4 | None = None
        # UIDs delivered (or failed) in this session: with mark_seen=False the mails stay
        # UNSEEN on the server, and a mail that can't be processed must not be retried
        # on every poll.
        self._handled_uids: set[str] = set()

    async def __aenter__(self) -> Self:
        """Connect to email server with configured protocol."""
        import ssl

        import aioimaplib

        # aioimaplib connects in the constructor, so the client is created here.
        if self.config.ssl:
            ssl_context = ssl.create_default_context()
            self._client = aioimaplib.IMAP4_SSL(
                self.config.host, self.config.port, ssl_context=ssl_context
            )
        else:
            self._client = aioimaplib.IMAP4(self.config.host, self.config.port)
        await self._client.wait_hello_from_server()
        response = await self._client.login(
            self.config.username, self.config.password.get_secret_value()
        )
        if response.result != "OK":
            msg = f"IMAP login failed: {_text(response.lines)}"
            raise RuntimeError(msg)
        response = await self._client.select(self.config.folder)
        if response.result != "OK":
            msg = f"Cannot select folder {self.config.folder!r}: {_text(response.lines)}"
            raise RuntimeError(msg)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close connection and cleanup."""
        self._stop_event.set()
        if self._client is None:
            return
        try:
            await self._client.close()
            await self._client.logout()
        except Exception:
            logger.exception("Error during email client cleanup")
        self._client = None

    def _build_search_criteria(self) -> str:
        """Build IMAP search string from filters."""
        # UNSEEN in both modes: with mark_seen the delivered mails are flagged \Seen,
        # without it the session remembers their UIDs.
        criteria = ["UNSEEN"]

        for key, value in self.config.filters.items():
            match key.upper():
                case "FROM" | "SUBJECT" | "TO" as criterion:
                    criteria.append(f"{criterion} {_quote(value)}")
                case _:
                    logger.warning("Unsupported email filter: %s", key)

        return " ".join(criteria)

    def _process_email(self, email_bytes: bytes) -> EventData:
        from email import policy
        from email.message import EmailMessage
        from email.parser import BytesParser

        if self.config.max_size and len(email_bytes) > self.config.max_size:
            msg = f"Email exceeds size limit of {self.config.max_size} bytes"
            raise ValueError(msg)

        # The default policy decodes RFC 2047 headers and the body's charset.
        email_msg = BytesParser(policy=policy.default).parsebytes(email_bytes)
        assert isinstance(email_msg, EmailMessage)
        body = email_msg.get_body(preferencelist=("plain", "html"))
        content = body.get_content() if body is not None else ""

        meta = {"date": email_msg["date"], "message_id": email_msg["message-id"]}
        return EmailEventData(
            source=self.config.name,
            subject=str(email_msg["subject"] or ""),
            sender=str(email_msg["from"] or ""),
            body=content,
            metadata=meta,
        )

    async def _wait(self, seconds: float) -> None:
        """Sleep until the next check, or until the source is stopped."""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._stop_event.wait(), seconds)

    async def events(self) -> AsyncGenerator[EventData]:
        """Monitor inbox and yield new email events."""
        if self._client is None:
            msg = "EmailEventSource must be entered before iterating events"
            raise RuntimeError(msg)
        client = self._client
        # FETCH RFC822 sets \Seen on the server; BODY.PEEK[] leaves the flags alone.
        fetch_item = "(RFC822)" if self.config.mark_seen else "(BODY.PEEK[])"
        while not self._stop_event.is_set():
            try:
                response = await client.uid_search(self._build_search_criteria())
                if response.result != "OK":
                    msg = f"IMAP search failed: {_text(response.lines)}"
                    raise RuntimeError(msg)  # noqa: TRY301
                uids = response.lines[0].decode().split() if response.lines else []

                for uid in uids:
                    if uid in self._handled_uids:
                        continue
                    self._handled_uids.add(uid)
                    try:
                        fetched = await client.uid("fetch", uid, fetch_item)
                        email_bytes = next(
                            (bytes(line) for line in fetched.lines if isinstance(line, bytearray)),
                            None,
                        )
                        if email_bytes is None:
                            continue
                        event = self._process_email(email_bytes)
                        if self.config.mark_seen:
                            await client.uid("store", uid, "+FLAGS", "(\\Seen)")
                        yield event
                    except Exception:
                        logger.exception("Error processing email %s", uid)

                await self._wait(self.config.check_interval)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error checking emails")
                await self._wait(self.config.check_interval)


def _quote(value: str) -> str:
    """Quote a value as an IMAP quoted string."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _text(lines: list[Any]) -> str:
    return " ".join(
        line.decode(errors="replace") if isinstance(line, (bytes, bytearray)) else str(line)
        for line in lines
    )
