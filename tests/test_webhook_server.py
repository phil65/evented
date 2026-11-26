from http import HTTPStatus
import logging
import socket
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from evented.webhook_watcher import WebhookEventSource
from evented_config import WebhookConfig


if TYPE_CHECKING:
    import pytest


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def test_binds_loopback_by_default() -> None:
    config = WebhookConfig(name="w", port=_free_port(), path="/hook")
    assert config.host == "127.0.0.1"
    async with WebhookEventSource(config) as source:
        assert source.server is not None
        assert source.server.config.host == "127.0.0.1"


async def test_warns_without_secret_on_a_public_host(caplog: pytest.LogCaptureFixture) -> None:
    config = WebhookConfig(name="w", port=_free_port(), path="/hook", host="0.0.0.0")
    with caplog.at_level(logging.WARNING):
        async with WebhookEventSource(config):
            pass
    assert "without a secret" in caplog.text


def test_invalid_json_is_a_client_error() -> None:
    source = WebhookEventSource(WebhookConfig(name="w", port=8098, path="/hook"))
    response = TestClient(source.app).post("/hook", content=b"{not json")
    assert response.status_code == HTTPStatus.BAD_REQUEST
