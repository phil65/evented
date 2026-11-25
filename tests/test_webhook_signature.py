from __future__ import annotations

import hashlib
import hmac
from http import HTTPStatus
import json

from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest

from evented.webhook_watcher import WebhookEventSource
from evented_config import WebhookConfig


SECRET = "s3cret"
PAYLOAD = json.dumps({"action": "opened"}).encode()


def _sig(algorithm: str) -> str:
    return hmac.new(SECRET.encode(), PAYLOAD, getattr(hashlib, algorithm)).hexdigest()


@pytest.fixture
def source() -> WebhookEventSource:
    config = WebhookConfig(name="gh", port=8099, path="/hook", secret=SecretStr(SECRET))
    return WebhookEventSource(config)


@pytest.mark.parametrize(
    "headers",
    [
        {"X-Hub-Signature-256": f"sha256={_sig('sha256')}"},  # GitHub (current)
        {"X-Hub-Signature": f"sha1={_sig('sha1')}"},  # GitHub (legacy)
        {"X-Hub-Signature": _sig("sha256")},  # bare hex (previous behaviour)
    ],
)
def test_valid_signatures_are_accepted(source: WebhookEventSource, headers: dict[str, str]):
    response = TestClient(source.app).post("/hook", content=PAYLOAD, headers=headers)
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"status": "ok"}
    assert source._queue.qsize() == 1


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-Hub-Signature-256": "sha256=" + "0" * 64},
        {"X-Hub-Signature-256": f"md5={_sig('sha256')}"},
    ],
)
def test_invalid_signatures_are_rejected(source: WebhookEventSource, headers: dict[str, str]):
    response = TestClient(source.app).post("/hook", content=PAYLOAD, headers=headers)
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert source._queue.qsize() == 0
