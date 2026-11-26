"""Webhook event source."""

import asyncio
from typing import TYPE_CHECKING, Self

from evented.base import EventSource
from evented.event_data import EventData, WebhookEventData
from evented.log import get_logger


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from types import TracebackType

    import uvicorn

    from evented_config import WebhookConfig


logger = get_logger(__name__)


def _is_loopback(host: str) -> bool:
    import ipaddress

    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class WebhookEventSource(EventSource):
    """Listens for webhook events on configured endpoint.

    Received events wait in an unbounded queue until `events()` takes them: a flood of
    requests (or a consumer that stops reading) grows memory. Bind to loopback or set a
    `secret` on public interfaces.
    """

    def __init__(self, config: WebhookConfig):
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse

        self.config = config
        self.app = FastAPI()
        self._queue = asyncio.Queue[EventData]()
        self.server: uvicorn.Server | None = None
        self._server_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

        async def handle_webhook(request: Request):
            if self.config.secret:  # Verify signature if secret configured
                # GitHub & co. send `X-Hub-Signature-256: sha256=<hex>` (current) and
                # `X-Hub-Signature: sha1=<hex>` (legacy).
                signature = request.headers.get("X-Hub-Signature-256") or request.headers.get(
                    "X-Hub-Signature"
                )
                if not self._verify_signature(await request.body(), signature):
                    return JSONResponse({"status": "invalid signature"}, status_code=401)

            try:
                payload = await request.json()
            except ValueError:  # json.JSONDecodeError, UnicodeDecodeError
                return JSONResponse({"status": "invalid JSON"}, status_code=400)
            event = WebhookEventData.create(source=self.config.name, payload=payload)
            await self._queue.put(event)
            return {"status": "ok"}

        # Annotations are strings (PEP 563) and Request is not importable from module
        # globals, so give FastAPI the real class to detect the request parameter.
        handle_webhook.__annotations__["request"] = Request
        self.app.post(config.path)(handle_webhook)

    async def __aenter__(self) -> Self:
        """Start webhook server."""
        import uvicorn

        self._stop_event.clear()
        host = self.config.host
        if not self.config.secret and not _is_loopback(host):
            logger.warning(
                "Webhook %r listens on %s without a secret: anyone who can reach it can "
                "inject events",
                self.config.name,
                host,
            )
        cfg = uvicorn.Config(self.app, host=host, port=self.config.port, log_level="error")
        self.server = uvicorn.Server(config=cfg)
        # serve() only returns on shutdown, so run it in the background.
        self._server_task = asyncio.create_task(self.server.serve())
        while not self.server.started and not self._server_task.done():
            await asyncio.sleep(0.01)
        if self._server_task.done():
            self._server_task.result()  # Re-raise startup errors
            msg = f"Webhook server failed to start on port {self.config.port}"
            raise RuntimeError(msg)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Stop webhook server."""
        self._stop_event.set()
        if self.server:
            self.server.should_exit = True
        if self._server_task:
            await self._server_task
        self.server = None
        self._server_task = None

    async def events(self) -> AsyncGenerator[EventData]:
        """Yield events as they arrive."""
        stop = asyncio.ensure_future(self._stop_event.wait())
        get: asyncio.Future[EventData] | None = None
        try:
            while not self._stop_event.is_set():
                get = asyncio.ensure_future(self._queue.get())
                await asyncio.wait({get, stop}, return_when=asyncio.FIRST_COMPLETED)
                if not get.done():
                    break
                yield get.result()
        finally:
            stop.cancel()
            if get is not None:
                get.cancel()

    def _verify_signature(self, payload: bytes, signature: str | None) -> bool:
        """Verify an HMAC signature of the payload.

        Accepts `sha256=<hex>` (GitHub's `X-Hub-Signature-256`), `sha1=<hex>` (legacy
        `X-Hub-Signature`) and a bare SHA-256 hex digest.
        """
        import hashlib
        import hmac

        if not signature or not self.config.secret:
            return False
        algorithm, sep, digest = signature.strip().partition("=")
        if not sep:
            algorithm, digest = "sha256", signature.strip()
        if algorithm not in {"sha256", "sha1"}:
            return False
        key = self.config.secret.get_secret_value().encode()
        expected = hmac.new(key, payload, getattr(hashlib, algorithm)).hexdigest()
        return hmac.compare_digest(digest, expected)
