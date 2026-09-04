"""Server-Sent Events (SSE) broadcasting over Redis Pub/Sub.

The Celery worker runs in a separate process from the API, so it cannot call
an in-process broadcast. Redis is the glue: the worker *publishes* lightweight
events (``{type, file_id}``) to a fixed channel; the API process *subscribes*
and relays every message to all open SSE connections. The frontend re-fetches
the REST lists on receipt, so events carry no payload beyond an identifier.
"""

import asyncio
import json
from collections.abc import AsyncIterator

import redis.asyncio as redis_async

from src.config import settings

# The Redis channel all file/alert events are published to.
EVENT_CHANNEL = "file-events"


def _redis_client() -> redis_async.Redis:
    """A connection reused by the process (pub from the worker, sub from API)."""
    return redis_async.from_url(settings.redis_url, decode_responses=True)


def _publish_payload(event_type: str, file_id: str) -> str:
    """Encode one event the way the worker publishes it (and clients parse it)."""
    return json.dumps({"type": event_type, "file_id": file_id})


async def publish_event(event_type: str, file_id: str) -> None:
    """Publish one compact event to the broadcast channel (worker side)."""
    client = _redis_client()
    try:
        await client.publish(EVENT_CHANNEL, _publish_payload(event_type, file_id))
    finally:
        await client.aclose()


def _sse_frame(payload: str) -> str:
    """Build an SSE frame: a named ``file_event`` whose ``data`` is the JSON body.

    The frame reaches the browser as `event: file_event` + `data: {...}`, so the
    client's addEventListener("file_event") receives ``{type, file_id}`` verbatim.
    """
    return f"event: file_event\ndata: {payload}\n\n"


async def stream_event_source() -> AsyncIterator[str]:
    """Relay all channel events to one SSE client, with a keep-alive heartbeat.

    The subscribe/read loop lives on the same event loop the API runs on; when
    the client disconnects, Starlette cancels this generator and the blocked
    ``get_message`` raises ``CancelledError``, unwinding the cleanup below.
    Heartbeat comments keep intermediate proxies from timing the connection out.
    """
    client = _redis_client()
    pubsub = client.pubsub()
    await pubsub.subscribe(EVENT_CHANNEL)

    try:
        while True:
            try:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=15.0
                )
            except asyncio.CancelledError:
                break

            if message is None:
                # Heartbeat: send a comment so the stream stays alive.
                yield ": keep-alive\n\n"
                continue
            if message.get("type") == "message":
                yield _sse_frame(message["data"])
    finally:
        await pubsub.unsubscribe(EVENT_CHANNEL)
        await pubsub.aclose()
        await client.aclose()