"""Local file storage service.

Encapsulates everything related to storing/reading/removing uploaded files on
disk, keeping the database layer free of filesystem concerns.

Uploads are streamed to disk in chunks instead of being buffered entirely in
memory, so large files don't blow up the process RAM.
"""

import mimetypes
from pathlib import Path

from fastapi import UploadFile

CHUNK_SIZE = 64 * 1024


class StorageError(Exception):
    """Raised when a stored-file path is invalid or otherwise unusable."""


class FileTooLargeError(StorageError):
    """Raised when a streamed upload exceeds the caller-provided size cap."""


class StorageService:
    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def resolve(self, stored_name: str) -> Path:
        """Resolve a stored name to an absolute path within the storage dir.

        Guards against path traversal: stored names are server-generated
        (uuid + extension), but we never trust caller input for paths.
        """
        base = self.storage_dir.resolve()
        path = (self.storage_dir / stored_name).resolve()
        if not path.is_relative_to(base):
            raise StorageError("Invalid stored file name")
        return path

    async def save(
        self,
        upload_file: UploadFile,
        stored_name: str,
        max_size: int | None = None,
    ) -> tuple[int, str]:
        """Stream an upload to disk in chunks.

        Stops and removes the partial file as soon as ``max_size`` is
        exceeded instead of buffering/writing the whole body, so oversized
        uploads cost O(cap) disk+time rather than O(body). Returns
        (size_in_bytes, mime_type) so the caller can persist both.
        """
        path = self.resolve(stored_name)
        mime_type = (
            upload_file.content_type
            or mimetypes.guess_type(stored_name)[0]
            or "application/octet-stream"
        )

        size = 0
        try:
            with path.open("wb") as fh:
                while chunk := await upload_file.read(CHUNK_SIZE):
                    size += len(chunk)
                    if max_size is not None and size > max_size:
                        raise FileTooLargeError(
                            f"File exceeds the {max_size} byte upload limit"
                        )
                    fh.write(chunk)
        except FileTooLargeError:
            path.unlink(missing_ok=True)
            raise
        return size, mime_type

    def path_for(self, stored_name: str) -> Path:
        """Absolute path for reading/downloading a stored file."""
        return self.resolve(stored_name)

    def delete(self, stored_name: str) -> None:
        path = self.resolve(stored_name)
        if path.exists():
            path.unlink()
