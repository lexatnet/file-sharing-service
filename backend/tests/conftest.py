"""Shared fixtures for the backend test suite.

Storage is exercised against an in-process moto S3 server (a local HTTP
server, not the network), so tests run without MinIO while still exercising
the real boto3 multipart API — including custom regions like ``ru-1``.
"""

import os

import pytest
from moto.server import ThreadedMotoServer

from src.config import Settings
from src.storage import S3StorageService

# Small default chunk so multipart tests exercise several parts without big
# payloads. Applied before Settings is constructed (part_size is read once).
os.environ.setdefault("S3_PART_SIZE", "5")

# moto does not support custom regions (like the app's ``ru-1``): it rejects
# them at CreateBucket. Pin a real AWS region for the tests.
os.environ.setdefault("SERVICE_S3_FILES_REGION", "us-east-1")


@pytest.fixture
def s3_def() -> S3StorageService:
    """Yield a ready S3StorageService backed by a throwaway moto server."""
    server = ThreadedMotoServer(ip_address="127.0.0.1", port=0)
    server.start()
    host, port = server.get_host_and_port()
    base = f"http://{host}:{port}"
    fixture_env: dict[str, str] = {}
    try:
        old_endpoint = os.environ.get("S3_ENDPOINT_URL")
        old_public = os.environ.get("S3_PUBLIC_ENDPOINT")
        old_region = os.environ.get("SERVICE_S3_FILES_REGION")
        os.environ["S3_ENDPOINT_URL"] = base
        os.environ["S3_PUBLIC_ENDPOINT"] = base
        # moto only understands real AWS regions; the app's ``ru-1`` would be
        # rejected at CreateBucket — force us-east-1 for the tests.

        os.environ["SERVICE_S3_FILES_REGION"] = "us-east-1"
        storage = S3StorageService(Settings())
        storage._client.create_bucket(Bucket=storage.bucket)
        yield storage
        os.environ.pop("S3_ENDPOINT_URL", None)
        if old_endpoint is not None:
            os.environ["S3_ENDPOINT_URL"] = old_endpoint
        os.environ.pop("S3_PUBLIC_ENDPOINT", None)
        if old_public is not None:
            os.environ["S3_PUBLIC_ENDPOINT"] = old_public
        os.environ.pop("SERVICE_S3_FILES_REGION", None)
        if old_region is not None:
            os.environ["SERVICE_S3_FILES_REGION"] = old_region
    finally:
        server.stop()


@pytest.fixture
def s3(s3_def):
    return s3_def


# S3 refuses to assemble a multipart object whose (non-last) parts are
# smaller than 5 MiB — the smallest legal multipart chunk size. Full-flow
# tests (the ones that call ``complete``) need a service that chunks at that
# size, while most tests keep the tiny ``part_size`` from the module setup.
S3_MIN_PART = 5 * 1024 * 1024  # 5 MiB


def make_big_part_storage(s3: S3StorageService) -> S3StorageService:

    """Make a sibling service with a legal multipart part size, sharing the moto
    server the ``s3`` fixture points at (its env vars are still live)."""

    old = os.environ.get("S3_PART_SIZE")
    os.environ["S3_PART_SIZE"] = str(S3_MIN_PART)
    try:
        storage = S3StorageService(Settings())
    finally:
        if old is None:
            os.environ.pop("S3_PART_SIZE", None)
        else:
            os.environ["S3_PART_SIZE"] = old
    return storage