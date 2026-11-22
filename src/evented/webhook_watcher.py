"""Webhook event source."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Self

from evented.base import EventSource
from evented.event_data import EventData, WebhookEventData


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from types import TracebackType

    import uvicorn

    from evented_config import WebhookConfig


class WebhookEventSource(EventSource):
    """Listens for webhook events on configured endpoint."""

    def __init__(self, config: WebhookConfig):
        from fastapi import FastAPI, Request

        self.config = config
        self.app = FastAPI()
        self._queue = asyncio.Queue[EventData]()
        self.server: uvicorn.Server | None = None
        self._server_task: asyncio.Task[None] | None = None

        async def handle_webhook(request: Request):
            if self.config.secret:  # Verify signature if secret configured
                signature = request.headers.get("X-Hub-Signature")
                if not self._verify_signature(await request.body(), signature):
                    return {"status": "invalid signature"}

            payload = await request.json()  # Process payload
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

        cfg = uvicorn.Config(self.app, host="0.0.0.0", port=self.config.port, log_level="error")
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
        if self.server:
            self.server.should_exit = True
        if self._server_task:
            await self._server_task
        self.server = None
        self._server_task = None

    async def events(self) -> AsyncGenerator[EventData]:
        """Yield events as they arrive."""
        while True:
            event = await self._queue.get()
            yield event

    def _verify_signature(self, payload: bytes, signature: str | None) -> bool:
        """Verify webhook signature."""
        import hashlib
        import hmac

        if not signature or not self.config.secret:
            return False
        key = self.config.secret.get_secret_value().encode()
        expected = hmac.new(key, payload, hashlib.sha256).hexdigest()

        return hmac.compare_digest(signature, expected)
