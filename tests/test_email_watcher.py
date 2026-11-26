from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any

from pydantic import SecretStr
import pytest

from evented.email_watcher import EmailEventSource
from evented_config import EmailConfig


if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from aioimaplib.imap_testing_server import MockImapServer

    from evented.event_data import EmailEventData


USER = "user@example.com"


def _mock() -> Any:
    # The module calls asyncio.get_event_loop() at import (a default argument), which
    # fails without a running loop on Python >= 3.14: import it inside the tests.
    from aioimaplib import imap_testing_server

    return imap_testing_server


@pytest.fixture
async def imap(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[MockImapServer, int]]:
    mock = _mock()
    search = mock.ImapProtocol.search

    def search_unseen(self: Any, tag: str, *args: str) -> None:
        # The mock knows no UNSEEN: map it to the equivalent UNKEYWORD \Seen.
        mapped = [
            a for arg in args for a in (("UNKEYWORD", "\\Seen") if arg == "UNSEEN" else (arg,))
        ]
        search(self, tag, *mapped)

    monkeypatch.setattr(mock.ImapProtocol, "search", search_unseen)
    server = mock.MockImapServer(loop=asyncio.get_running_loop())
    srv = await server.run_server(host="127.0.0.1", port=0)
    port = srv.sockets[0].getsockname()[1]
    yield server, port
    srv.close()
    await srv.wait_closed()


def _config(port: int, **kwargs: Any) -> EmailConfig:
    return EmailConfig(
        name="mail",
        host="127.0.0.1",
        port=port,
        username=USER,
        password=SecretStr("pw"),
        ssl=False,
        check_interval=1,
        **kwargs,
    )


async def _collect(source: EmailEventSource, count: int, timeout: float = 3) -> list[Any]:
    events: list[Any] = []

    async def run() -> None:
        async for event in source.events():
            events.append(event)
            if len(events) >= count:
                return

    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(run(), timeout)
    return events


async def test_delivers_an_email_and_marks_it_seen(imap: tuple[MockImapServer, int]) -> None:
    server, port = imap
    server.receive(
        _mock().Mail.create(
            [USER], mail_from="alice@example.com", subject="héllo", content="body text"
        )
    )
    async with EmailEventSource(_config(port)) as source:
        events = await _collect(source, 1)
        assert len(events) == 1
        event: EmailEventData = events[0]
        assert event.subject == "héllo"
        assert "alice@example.com" in event.sender
        assert event.body.strip() == "body text"
        # Marked seen: the next poll delivers nothing.
        assert await _collect(source, 1, timeout=1.5) == []


async def test_mark_seen_false_delivers_each_email_once(
    imap: tuple[MockImapServer, int],
) -> None:
    server, port = imap
    server.receive(_mock().Mail.create([USER], mail_from="a@example.com", subject="s", content="x"))
    async with EmailEventSource(_config(port, mark_seen=False)) as source:
        assert len(await _collect(source, 1)) == 1
        assert await _collect(source, 1, timeout=1.5) == []
    # Not flagged \Seen on the server.
    async with EmailEventSource(_config(port, mark_seen=False)) as source:
        assert len(await _collect(source, 1)) == 1


async def test_latin1_email_is_decoded(imap: tuple[MockImapServer, int]) -> None:
    server, port = imap
    server.receive(
        _mock().Mail.create(
            [USER], mail_from="a@example.com", subject="s", content="café", encoding="latin-1"
        )
    )
    async with EmailEventSource(_config(port)) as source:
        events = await _collect(source, 1)
    assert events[0].body.strip() == "café"


async def test_search_criteria() -> None:
    source = EmailEventSource(_config(1, filters={"from": 'a"b\\c', "subject": "hi"}))
    assert source._build_search_criteria() == 'UNSEEN FROM "a\\"b\\\\c" SUBJECT "hi"'
    assert EmailEventSource(_config(1))._build_search_criteria() == "UNSEEN"
    assert EmailEventSource(_config(1, mark_seen=False))._build_search_criteria() == "UNSEEN"
