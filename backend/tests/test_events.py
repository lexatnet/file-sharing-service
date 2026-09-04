"""SSE event broadcasting: pub/sub plumbing and SSE frame encoding.

The full Redis round-trip only runs if a Redis is reachable (e.g. the compose
stack) and is skipped otherwise, so the unit suite stays green without infra.
"""

import asyncio
import json

import pytest

from src.config import settings
from src.events import (
    _publish_payload,
    _sse_frame,
    publish_event,
    stream_event_source,
)


async def redis_is_available() -> bool:
    import redis.asyncio as redis_async

    client = redis_async.from_url(settings.redis_url, decode_responses=True)
    try:
        await client.ping()
        return True
    except Exception:
        return False
    finally:
        await client.aclose()


redis_available = pytest.mark.skipif(
    not __import__("asyncio").run(redis_is_available()),
    reason="Redis not reachable",
)


def test_publish_payload_matches_what_client_parses():
    payload = json.loads(_publish_payload("file_processed", "file-123"))
    assert payload == {"type": "file_processed", "file_id": "file-123"}


def test_sse_frame_is_a_named_event_with_verbatim_payload():
    payload = _publish_payload("alert_created", "file-9")
    frame = _sse_frame(payload)
    assert frame.startswith("event: file_event\n")
    assert ("\ndata: " in frame) and frame.endswith("\n\n")
    # The data line carries the exact JSON the client JSON.parses into FileEvent.
    data_line = frame.split("\ndata: ", 1)[1].rsplit("\n", 1)[0]
    assert json.loads(data_line)["type"] == "alert_created"


@redis_available
async def test_publish_then_stream_relays_event():
    import redis.asyncio as redis_async

    # Subscribe a listener directly, then publish — assert the frame arrives.
    client = redis_async.from_url(settings.redis_url, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe("file-events")

    await publish_event("file_processed", "file-123")

    found = None
    for _ in range(20):
        message = await pubsub.get_message(
            ignore_subscribe_messages=True, timeout=1.0
        )
        if message and message.get("type") == "message":
            found = json.loads(message["data"])
            break
        await asyncio.sleep(0.05)

    await pubsub.unsubscribe("file-events")
    await pubsub.aclose()
    await client.aclose()

    assert found == {"type": "file_processed", "file_id": "file-123"}