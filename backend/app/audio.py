from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.errors import AppError


MIME_SUFFIXES = {
    "audio/webm": ".webm",
    "audio/mp4": ".mp4",
    "audio/x-m4a": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
}
READ_CHUNK_BYTES = 1024 * 1024
DECISION_SUPPORT_DIR_PREFIX = "decision-support-"


@dataclass(frozen=True, slots=True)
class StoredAudio:
    path: str
    size: int
    content_type: str


class AudioStorage:
    def __init__(self, root: str, max_bytes: int) -> None:
        self.root = Path(root).expanduser().resolve()
        self.max_bytes = max_bytes

    def ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def store(self, upload: UploadFile, session_id: str) -> StoredAudio:
        content_type = (upload.content_type or "").split(";", 1)[0].strip().lower()
        suffix = MIME_SUFFIXES.get(content_type)
        if suffix is None:
            raise AppError(400, "UNSUPPORTED_AUDIO_TYPE", "不支持此音频类型。")

        session_dir = self._session_dir(session_id)
        destination = (session_dir / f"{uuid4()}{suffix}").resolve()
        self._require_within_root(destination)
        size = 0
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as output:
                while chunk := upload.file.read(READ_CHUNK_BYTES):
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise AppError(
                            400,
                            "AUDIO_TOO_LARGE",
                            "音频文件超过大小限制。",
                        )
                    output.write(chunk)
            return StoredAudio(str(destination), size, content_type)
        except AppError:
            self._remove_partial(destination, session_dir)
            raise
        except (OSError, ValueError) as exc:
            self._remove_partial(destination, session_dir)
            raise AppError(500, "STORAGE_ERROR", "音频文件无法保存。") from exc

    def existing_path(self, raw_path: str | None) -> Path | None:
        if not raw_path:
            return None
        try:
            path = Path(raw_path).expanduser().resolve()
            self._require_within_root(path)
        except (OSError, ValueError):
            return None
        return path if path.is_file() else None

    def delete_file(self, raw_path: str) -> None:
        try:
            path = Path(raw_path).expanduser().resolve()
            self._require_within_root(path)
            path.unlink(missing_ok=True)
            parent = path.parent
            if parent != self.root and parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
        except (OSError, ValueError) as exc:
            raise AppError(500, "STORAGE_ERROR", "临时音频无法清理。") from exc

    def best_effort_delete_file(self, raw_path: str) -> bool:
        try:
            self.delete_file(raw_path)
            return True
        except AppError:
            return False

    def delete_session_dir(self, session_id: str) -> bool:
        try:
            session_dir = self._session_dir(session_id)
            if session_dir.exists():
                shutil.rmtree(session_dir)
            return True
        except (OSError, ValueError):
            return False

    def delete_orphan_decision_support_dirs(self) -> tuple[int, int]:
        deleted = 0
        failed = 0
        try:
            entries = list(self.root.iterdir()) if self.root.exists() else []
        except OSError:
            return 0, 1
        for entry in entries:
            if not entry.is_dir() or not entry.name.startswith(
                DECISION_SUPPORT_DIR_PREFIX
            ):
                continue
            try:
                resolved = entry.resolve()
                self._require_within_root(resolved)
                shutil.rmtree(resolved)
                deleted += 1
            except (OSError, ValueError):
                failed += 1
        return deleted, failed

    def _session_dir(self, session_id: str) -> Path:
        path = (self.root / session_id).resolve()
        self._require_within_root(path)
        return path

    def _require_within_root(self, path: Path) -> None:
        if not path.is_relative_to(self.root):
            raise ValueError("audio path escaped configured storage root")

    @staticmethod
    def _remove_partial(destination: Path, session_dir: Path) -> None:
        try:
            destination.unlink(missing_ok=True)
            if session_dir.exists() and not any(session_dir.iterdir()):
                session_dir.rmdir()
        except OSError:
            pass
