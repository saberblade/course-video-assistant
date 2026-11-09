"""把上传的文件按块写到临时目录，超过大小立刻停下并删掉。"""

from __future__ import annotations

import errno
from pathlib import Path

from fastapi import UploadFile

from app.errors import AppError


def save_upload(upload: UploadFile, destination: Path, max_bytes: int) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        with destination.open("wb") as handle:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                if total + len(chunk) > max_bytes:
                    raise AppError(413, "FILE_TOO_LARGE", "视频不能超过200 MiB，请换较小文件", False)
                handle.write(chunk)
                total += len(chunk)
    except AppError:
        destination.unlink(missing_ok=True)
        raise
    except OSError as exc:
        destination.unlink(missing_ok=True)
        if exc.errno == errno.ENOSPC:
            raise AppError(507, "STORAGE_FULL", "磁盘空间不足，请联系系统工程师", True) from exc
        raise
    return total
