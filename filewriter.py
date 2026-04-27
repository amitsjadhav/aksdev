“””
file_writer.py — Writes parsed SWIFT messages to Databricks Volume mount paths.

The Databricks Volume is expected to be mounted on the AKS pod at the path
returned by the routing table (e.g. /dbfs/mnt/swift/mt515/).

File naming convention:
<MESSAGE_TYPE>*<REFERENCE>*<TIMESTAMP_UTC>_<MSGID_HEX8>.txt

Example:
MT515_REF20240101_20240615T143022_1A2B3C4D.txt
“””

from **future** import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from swift_parser import SwiftMessage

logger = logging.getLogger(**name**)

class FileWriteError(IOError):
pass

class DatabricksFileWriter:
“””
Writes raw SWIFT message content to the correct Volume mount path.
Creates subdirectories on first write.
“””

```
def write(
    self,
    message: SwiftMessage,
    landing_path: str,
    raw_bytes: bytes,
) -> str:
    """
    Persist the message to `landing_path` and return the full file path written.

    Args:
        message:      Parsed SwiftMessage (used for naming)
        landing_path: Directory path from routing table  e.g. /mnt/swift/mt515/
        raw_bytes:    Original raw bytes from MQ (written verbatim)

    Returns:
        Absolute path of the file written.

    Raises:
        FileWriteError: on any OS-level failure.
    """
    dest_dir = Path(landing_path)
    self._ensure_dir(dest_dir)

    filename  = self._build_filename(message, raw_bytes)
    full_path = dest_dir / filename

    try:
        full_path.write_bytes(raw_bytes)
        logger.info(
            "Written %s  type=%s  ref=%s  bytes=%d",
            full_path, message.message_type, message.reference, len(raw_bytes),
        )
    except OSError as exc:
        raise FileWriteError(
            f"Cannot write to '{full_path}': {exc}"
        ) from exc

    return str(full_path)

# ── helpers ────────────────────────────────────────────────────────────────

@staticmethod
def _ensure_dir(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise FileWriteError(f"Cannot create directory '{path}': {exc}") from exc

@staticmethod
def _build_filename(message: SwiftMessage, raw_bytes: bytes) -> str:
    """
    Build a collision-resistant, human-readable filename.
    Uses first 8 hex chars of SHA-1 of the raw content as a uniqueness suffix.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    ref       = _safe_name(message.reference) or "NOREF"
    msg_type  = _safe_name(message.message_type) or "UNKNOWN"
    checksum  = hashlib.sha1(raw_bytes).hexdigest()[:8].upper()
    return f"{msg_type}_{ref}_{timestamp}_{checksum}.txt"
```

# ── util ───────────────────────────────────────────────────────────────────────

def *safe_name(value: str) -> str:
“”“Strip characters unsafe for filenames.”””
return “”.join(c for c in value.upper() if c.isalnum() or c in (”*”, “-”))[:40]