“””
listener.py — Orchestrates one full poll cycle:
1. Connect to IBM MQ
2. Drain queue (up to max_messages_per_poll)
3. For each message:
a. Decode bytes → string
b. Parse SWIFT → SwiftMessage
c. Validate it’s an MT5xx family message
d. Look up landing path from Databricks routing cache
e. Write file to Volume mount path
f. Log outcome (success / skip / error)
“””

from **future** import annotations

import logging
from typing import Optional

from config import Config
from databricks_client import RoutingTableClient
from file_writer import DatabricksFileWriter, FileWriteError
from mq_client import MQClient, MQConnectionError
from swift_parser import SwiftMessage, SwiftParser, SwiftParseError

logger = logging.getLogger(**name**)

class MQSwiftListener:
“””
Stateful listener.  Call `.poll()` in a loop (driven by main.py).
Holds a long-lived Databricks routing client with an in-memory cache.
Creates a fresh MQ connection per poll cycle for resilience.
“””

```
def __init__(self, cfg: Config) -> None:
    self._cfg     = cfg
    self._routing = RoutingTableClient(cfg.databricks)
    self._writer  = DatabricksFileWriter()
    self._parser  = SwiftParser()

def poll(self) -> None:
    """Execute one poll cycle. Errors are logged; nothing is re-raised."""
    logger.debug("Starting poll cycle")
    try:
        with MQClient(self._cfg.mq) as client:
            for raw_bytes, md in client.get_messages():
                self._handle_message(raw_bytes, md)
    except MQConnectionError as exc:
        logger.error("MQ connection error during poll: %s", exc)
    except Exception as exc:
        logger.error("Unexpected error during poll: %s", exc, exc_info=True)

# ── per-message processing ─────────────────────────────────────────────────

def _handle_message(self, raw_bytes: bytes, md) -> None:  # md: pymqi.MD
    msg_id_hex = md.MsgId.hex()

    # 1. Decode
    raw_text = self._decode(raw_bytes, msg_id_hex)
    if raw_text is None:
        return

    # 2. Parse
    message = self._parse(raw_text, msg_id_hex)
    if message is None:
        return

    # 3. Validate MT5xx family
    if not message.is_mt5xx():
        logger.info(
            "Skipping non-MT5xx message: type=%s  msgid=%s",
            message.message_type, msg_id_hex,
        )
        return

    # 4. Route
    landing_path = self._routing.get_landing_path(message.message_type)
    if landing_path is None:
        logger.warning(
            "No routing entry for type=%s — message dropped  msgid=%s",
            message.message_type, msg_id_hex,
        )
        return

    # 5. Write
    self._write(message, landing_path, raw_bytes, msg_id_hex)

# ── helpers ────────────────────────────────────────────────────────────────

@staticmethod
def _decode(raw_bytes: bytes, msg_id_hex: str) -> Optional[str]:
    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    logger.error("Cannot decode message bytes  msgid=%s", msg_id_hex)
    return None

@staticmethod
def _parse(raw_text: str, msg_id_hex: str) -> Optional[SwiftMessage]:
    try:
        return SwiftParser.parse(raw_text)
    except SwiftParseError as exc:
        logger.error("SWIFT parse error  msgid=%s: %s", msg_id_hex, exc)
        return None

def _write(
    self,
    message: SwiftMessage,
    landing_path: str,
    raw_bytes: bytes,
    msg_id_hex: str,
) -> None:
    try:
        file_path = self._writer.write(message, landing_path, raw_bytes)
        logger.info(
            "SUCCESS  type=%s  ref=%s  file=%s  msgid=%s",
            message.message_type, message.reference, file_path, msg_id_hex,
        )
    except FileWriteError as exc:
        logger.error(
            "File write failed  type=%s  path=%s  msgid=%s: %s",
            message.message_type, landing_path, msg_id_hex, exc,
        )
```