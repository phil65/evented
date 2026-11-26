# Evented

[![PyPI License](https://img.shields.io/pypi/l/evented.svg)](https://pypi.org/project/evented/)
[![Package status](https://img.shields.io/pypi/status/evented.svg)](https://pypi.org/project/evented/)
[![Monthly downloads](https://img.shields.io/pypi/dm/evented.svg)](https://pypi.org/project/evented/)
[![Distribution format](https://img.shields.io/pypi/format/evented.svg)](https://pypi.org/project/evented/)
[![Wheel availability](https://img.shields.io/pypi/wheel/evented.svg)](https://pypi.org/project/evented/)
[![Python version](https://img.shields.io/pypi/pyversions/evented.svg)](https://pypi.org/project/evented/)
[![Implementation](https://img.shields.io/pypi/implementation/evented.svg)](https://pypi.org/project/evented/)
[![Releases](https://img.shields.io/github/downloads/phil65/evented/total.svg)](https://github.com/phil65/evented/releases)
[![Github Contributors](https://img.shields.io/github/contributors/phil65/evented)](https://github.com/phil65/evented/graphs/contributors)
[![Github Forks](https://img.shields.io/github/forks/phil65/evented)](https://github.com/phil65/evented/forks)
[![Github Issues](https://img.shields.io/github/issues/phil65/evented)](https://github.com/phil65/evented/issues)
[![Github Issues](https://img.shields.io/github/issues-pr/phil65/evented)](https://github.com/phil65/evented/pulls)
[![Github Watchers](https://img.shields.io/github/watchers/phil65/evented)](https://github.com/phil65/evented/watchers)
[![Github Stars](https://img.shields.io/github/stars/phil65/evented)](https://github.com/phil65/evented/stars)
[![Github Repository size](https://img.shields.io/github/repo-size/phil65/evented)](https://github.com/phil65/evented)
[![Github last commit](https://img.shields.io/github/last-commit/phil65/evented)](https://github.com/phil65/evented/commits)
[![Github release date](https://img.shields.io/github/release-date/phil65/evented)](https://github.com/phil65/evented/releases)
[![Github language count](https://img.shields.io/github/languages/count/phil65/evented)](https://github.com/phil65/evented)
[![Github commits this month](https://img.shields.io/github/commit-activity/m/phil65/evented)](https://github.com/phil65/evented)
[![Package status](https://codecov.io/gh/phil65/evented/branch/main/graph/badge.svg)](https://codecov.io/gh/phil65/evented/)
[![PyUp](https://pyup.io/repos/github/phil65/evented/shield.svg)](https://pyup.io/repos/github/phil65/evented/)

[Read the documentation!](https://phil65.github.io/evented/)

**Async event sources that turn file changes, webhooks, emails and cron schedules into typed events.**

`evented` gives you a small set of asyncio event sources behind one interface, and an
`EventManager` that runs them and passes every event to your callbacks. Events are pydantic
models with a `to_prompt()` method, so they can go straight into an LLM agent.
Sources are configured with pydantic models (`evented_config`), so they can be loaded from
YAML/JSON and validated.

## Installation

```bash
pip install evented          # core (config models, manager, event types)
pip install "evented[all]"   # + watchfiles, fastapi/uvicorn, aioimaplib, croniter
```

Requires Python 3.13+. The backends of the sources are optional dependencies; the `all` extra
installs all of them.

## Quickstart

```python
import asyncio

from evented import EventData, EventManager


async def on_event(event: EventData) -> None:
    print(f"[{event.source}] {event.to_prompt()}")


async def main() -> None:
    async with EventManager(event_callbacks=[on_event]) as manager:
        await manager.add_file_watch("./src", extensions=[".py", ".md"], name="src")
        await manager.add_timed_event("*/5 * * * *", "Run the health check", name="cron")

        @manager.track("compute")
        async def compute(x: int) -> int:
            return x * 2

        await compute(21)  # prints "[compute] 42"
        await asyncio.sleep(60)  # edit a file in ./src meanwhile


asyncio.run(main())
```

### From configuration

`EventConfig` is a discriminated union over all config types (key: `type`):

```python
import asyncio

from pydantic import TypeAdapter

from evented import EventConfig, EventSource

raw = {"type": "time", "name": "daily", "schedule": "0 9 * * 1-5", "prompt": "Morning report"}
config = TypeAdapter(EventConfig).validate_python(raw)  # -> TimeEventConfig


async def main() -> None:
    async with EventSource.from_config(config) as source:
        async for event in source.events():
            print(event.to_prompt())


asyncio.run(main())
```

You can also pass a list of configs to the manager: `EventManager(configs=[...])`.

## Event sources

| Config (`type`) | Source | Backend | Event |
| --- | --- | --- | --- |
| `FileWatchConfig` (`file`) | `FileSystemEventSource` | watchfiles | `FileEventData` |
| `WebhookConfig` (`webhook`) | `WebhookEventSource` | FastAPI + uvicorn | `WebhookEventData` |
| `EmailConfig` (`email`) | `EmailEventSource` | aioimaplib (IMAP) | `EmailEventData` |
| `TimeEventConfig` (`time`) | `TimeEventSource` | croniter | `TimeEventData` |

The webhook source keeps received events in an unbounded queue until they are processed: bind
it to loopback (the default) or set a `secret` before exposing it.

## Features

- **One interface for every source**: each source is an async context manager with an
  `events()` async generator, so you can use it without the manager.
- **`EventManager`**: runs several sources at once, calls sync or async callbacks, and has
  shortcuts like `add_file_watch()`, `add_webhook()`, `add_email_watch()` and
  `add_timed_event()`. Callbacks run one at a time, in registration order (async callbacks
  are awaited in turn, not concurrently), so a slow callback holds up the others.
- **Function tracking**: `@manager.track()` emits a `FunctionResultEventData` for each call,
  with arguments, duration and success/error status in `metadata`.
- **Prompt templates**: `await event.format(config)` renders an event with the source's Jinja
  `template` (timestamp and metadata can be turned off).
- **Lightweight config package**: `evented_config` holds only the pydantic models, so you can
  import it in config schemas without pulling in the runtime.
