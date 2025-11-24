"""Webhook event source."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Self

from evented.base import EventSource
from evented.event_data import EventData


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from types import TracebackType

    from fastapi import Request

    from evented.configs import WebhookConfig


class WebhookEventSource(EventSource):
    """Listens for webhook events on configured endpoint."""

    def __init__(self, config: WebhookConfig):
        from fastapi import FastAPI

        self.config = config
        self.app = FastAPI()
        self._queue = asyncio.Queue[EventData]()

        @self.app.post(config.path)
        async def handle_webhook(request: Request):
            if self.config.secret:  # Verify signature if secret configured
                signature = request.headers.get("X-Hub-Signature")
                if not self._verify_signature(await request.body(), signature):
                    return {"status": "invalid signature"}

            payload = await request.json()  # Process payload
            event = EventData.create(source=self.config.name, content=payload)
            await self._queue.put(event)
            return {"status": "ok"}

    async def __aenter__(self) -> Self:
        """Start webhook server."""
        import uvicorn

        cfg = uvicorn.Config(self.app, host="0.0.0.0", port=self.config.port, log_level="error")
        self.server = uvicorn.Server(config=cfg)
        await self.server.serve()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Stop webhook server."""
        if self.server:
            await self.server.shutdown()

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
