"""Email event source."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Self

from evented.base import EventSource
from evented.event_data import EmailEventData
from evented.log import get_logger


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from types import TracebackType

    import aioimaplib

    from evented.configs import EmailConfig
    from evented.event_data import EventData

logger = get_logger(__name__)


class EmailEventSource(EventSource):
    """Monitors email inbox for events."""

    def __init__(self, config: EmailConfig):
        import ssl

        import aioimaplib

        self.config = config
        self._stop_event = asyncio.Event()

        # Create client object (no IO)
        if self.config.ssl:
            ssl_context = ssl.create_default_context()
            self._client: aioimaplib.IMAP4_SSL | aioimaplib.IMAP4 = aioimaplib.IMAP4_SSL(
                self.config.host, self.config.port, ssl_context=ssl_context
            )
        else:
            self._client = aioimaplib.IMAP4(self.config.host, self.config.port)

    async def __aenter__(self) -> Self:
        """Connect to email server with configured protocol."""
        await self._client.login(self.config.username, self.config.password.get_secret_value())
        await self._client.select(self.config.folder)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close connection and cleanup."""
        self._stop_event.set()
        try:
            await self._client.close()
            await self._client.logout()
        except Exception:
            logger.exception("Error during email client cleanup")

    def _build_search_criteria(self) -> str:
        """Build IMAP search string from filters."""
        criteria = ["UNSEEN"] if not self.config.mark_seen else []

        # Add configured filters
        for key, value in self.config.filters.items():
            # Convert filter keys to IMAP criteria
            match key.upper():
                case "FROM":
                    criteria.append(f'FROM "{value}"')
                case "SUBJECT":
                    criteria.append(f'SUBJECT "{value}"')
                case "TO":
                    criteria.append(f'TO "{value}"')
                case _:
                    logger.warning("Unsupported email filter: %s", key)

        return " ".join(criteria)

    def _process_email(self, email_bytes: bytes) -> EventData:
        from email.parser import BytesParser

        parser = BytesParser()
        email_msg = parser.parsebytes(email_bytes)
        if self.config.max_size and len(email_bytes) > self.config.max_size:
            msg = f"Email exceeds size limit of {self.config.max_size} bytes"
            raise ValueError(msg)

        # Extract content (prefer text/plain)
        content = ""
        for part in email_msg.walk():
            content_type = part.get_content_type()
            match content_type:
                case "text/plain":
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        content = payload.decode()
                    break
                case "text/html":
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        content = payload.decode()

        meta = {"date": email_msg["date"], "message_id": email_msg["message-id"]}
        return EmailEventData(
            source=self.config.name,
            subject=email_msg["subject"],
            sender=email_msg["from"],
            body=content,
            metadata=meta,
        )

    async def events(self) -> AsyncGenerator[EventData]:
        """Monitor inbox and yield new email events."""
        while not self._stop_event.is_set():
            try:
                search_criteria = self._build_search_criteria()
                _, messages = await self._client.search(search_criteria)

                for num in messages[0].split():  # Process each message
                    try:
                        # Fetch full message
                        _, msg_data = await self._client.fetch(num, "(RFC822)")
                        if not msg_data:
                            continue

                        email_bytes = msg_data[0][1]
                        event = self._process_email(email_bytes)

                        if self.config.mark_seen:  # Mark as seen if configured
                            await self._client.store(num, "+FLAGS", "\\Seen")

                        yield event

                    except Exception:
                        logger.exception("Error processing email")

                await asyncio.sleep(self.config.check_interval)  # Wait before next check

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error checking emails")
                await asyncio.sleep(self.config.check_interval)
