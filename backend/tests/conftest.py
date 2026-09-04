"""Shared fixtures for the backend test suite."""

import pytest

from src.storage import StorageService


@pytest.fixture
def storage(tmp_path) -> StorageService:
    return StorageService(tmp_path / "files")