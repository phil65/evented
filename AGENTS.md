# AGENTS.md

## Overview

`evented` is a small asyncio library of event sources (file changes, webhooks, IMAP email,
cron schedules) that turn external happenings into typed pydantic `EventData` objects, plus an
`EventManager` that runs sources and fans events out to callbacks. It was built to feed events
to LLM agents (every event has `to_prompt()`), and its configs are used by agentpool.
Two import packages ship in one distribution: `evented` (runtime) and `evented_config`
(config models only, so importing them is cheap).

## Architecture

- `src/evented_config/configs.py`: pydantic/schemez config models. `EventSourceConfig` base,
  subclasses `FileWatchConfig` (`type="file"`), `WebhookConfig` (`"webhook"`), `EmailConfig`
  (`"email"`), `TimeEventConfig` (`"time"`). `EventConfig` is the discriminated union on `type`.
  Each config's `get_event_source()` lazily imports and builds its source.
- `src/evented/base.py`: `EventSource` ABC (async context manager + `events()` async generator)
  and `EventSource.from_config()` factory (`match` on config type, rejects disabled configs).
- Sources (one per file, heavy deps imported lazily inside methods):
  - `file_watcher.py`: `FileSystemEventSource` (watchfiles `awatch`), `ExtensionFilter`.
  - `webhook_watcher.py`: `WebhookEventSource` (FastAPI app + uvicorn server run as a
    background task between `__aenter__`/`__aexit__`; events via an `asyncio.Queue`).
  - `email_watcher.py`: `EmailEventSource` (aioimaplib polling, `filters` -> IMAP criteria).
  - `timed_watcher.py`: `TimeEventSource` (croniter schedule, optional timezone/skip_missed).
- `src/evented/event_data.py`: `EventData` (abstract `to_prompt()`, frozen, Jinja `format()`
  via jinjarope using the config's `template`) and subclasses `FileEventData`, `EmailEventData`,
  `TimeEventData`, `WebhookEventData`, `FunctionResultEventData`.
- `src/evented/event_manager.py`: `EventManager`. `add_source(config)` enters the source and
  spawns a task that pulls `events()` and calls `emit_event()` -> all callbacks (sync or async).
  Convenience adders: `add_file_watch`, `add_webhook`, `add_timed_event`, `add_email_watch`.
  Decorators: `track()` (emits a `FunctionResultEventData` per call, success or error) and
  `poll()`. Usable as `async with EventManager(configs) as m:`.
- Helpers: `helpers.py` (`execute` sync/async callables, `run_background`), `log.py`
  (`get_logger`, prefixes `evented.`), `now.py` (`get_now`, UTC by default).

Flow: config -> `EventSource.from_config` -> `async with source` -> `events()` ->
`EventManager._process_events` -> `emit_event` -> callbacks.

## Where to look

| Task | Location |
| --- | --- |
| Add a new event source | new `src/evented/<x>_watcher.py`, config in `src/evented_config/configs.py` (add to `EventConfig` union), `base.py` factory, exports in both `__init__.py` |
| Change config fields / JSON schema | `src/evented_config/configs.py` |
| Event payload types / prompt text | `src/evented/event_data.py` |
| Callback dispatch, decorators | `src/evented/event_manager.py` |
| Public API | `src/evented/__init__.py`, `src/evented_config/__init__.py` |
| Tests | `tests/` (`test_manager.py`, `test_factory.py`, `test_time_events.py`, `test_context_managers.py`) |
| CI | `.github/workflows/build.yml`, `.github/workflows/documentation.yml` |
| Task shortcuts | `duties.py` |

## Commands

```bash
uv sync --all-extras                 # setup (default groups: dev, lint, docs)
uv run pytest                        # tests (asyncio_mode = "auto")
uv run ruff check . && uv run ruff format --check .
uv run ty check                      # type check, checks src/ only; warnings fail CI
uv run deptry src                    # declared vs imported dependencies
uv run mknodes build          # docs (or: uv run duty build / duty serve)
uv run duty lint                     # ruff fix + format + ty
uv build
```

CI (`build.yml`) runs `uv sync --all-extras --no-group docs --no-group lint`, ruff, `ty check`
and pytest with coverage on Linux/macOS/Windows for 3.13 and 3.14 (3.14 may fail).

## Conventions

- Python >= 3.13, `from __future__ import annotations` everywhere, PEP 695 generics/`type`.
- Typing-only imports go under `TYPE_CHECKING`. Optional deps (`watchfiles`, `fastapi`,
  `uvicorn`, `aioimaplib`, `croniter`) are imported inside functions so `import evented`
  works without the `all` extra.
- Config models subclass `schemez.Schema` (`extra="forbid"`, attribute docstrings become field
  descriptions), so unknown kwargs raise. Keep the field docstrings.
- Google-style docstrings, ruff line length 100, preview formatting.
- Tests: plain pytest functions, async tests need no marker.

## Specs

| Spec | URL | Targets | Code | Update check |
|---|---|---|---|---|
| IMAP4rev1 (via aioimaplib); messages parsed as RFC 5322 | https://www.rfc-editor.org/rfc/rfc3501 | IMAP4rev1 (RFC 3501) | `src/evented/email_watcher.py` | https://github.com/bamthomas/aioimaplib/releases |
| Cron expressions (croniter syntax) | https://github.com/pallets-eco/croniter | unpinned (tracks latest croniter) | `src/evented/timed_watcher.py` | same URL |
| Webhook HMAC signature | https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries | own scheme: bare hex HMAC-SHA256 of the body in `X-Hub-Signature` (GitHub sends `X-Hub-Signature-256: sha256=<hex>`, so GitHub deliveries do not verify as is) | `src/evented/webhook_watcher.py` (`_verify_signature`) | n/a |

## Pitfalls

- Copier-managed project (`.copier-answers.yml`, template `copier-phil65`): don't hand-edit
  template-owned files (workflows, `duties.py`, `.pre-commit-config.yaml`, most of
  `pyproject.toml`); add dependencies below the `# Only add below (Copier)` markers.
- Source backends need the `all` extra (`uv sync --all-extras`); tests rely on it.
- `EventData` is abstract: build events from a concrete subclass, never `EventData.create()`.
- FastAPI resolves handler annotations at runtime; with postponed annotations a
  `TYPE_CHECKING`-only type breaks routes (see the annotation fix in `webhook_watcher.py`).
- `WebhookEventSource` binds `0.0.0.0:<port>`; `EmailEventSource` talks to a real IMAP server.
  Unit tests must not start them against real services.
- `EventManager.poll()` registers observers in `_observers`, but nothing dispatches to them yet;
  `remove_source()` exits the source but doesn't cancel its processing task.
- Pre-commit (prek) runs ruff, ty and the full pytest suite on every commit.
