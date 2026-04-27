“””
databricks_client.py — Fetches message-type → landing-path routing from
Unity Catalog and caches the result to avoid per-message SQL round-trips.

Expected table schema (configurable names via Config):
CREATE TABLE <catalog>.<schema>.<routing_table> (
message_type   STRING  NOT NULL,   – e.g. “MT515”
landing_path   STRING  NOT NULL,   – e.g. “/Volumes/cat/schema/vol/swift/mt515/”
is_active      BOOLEAN DEFAULT TRUE,
description    STRING
);
“””

from **future** import annotations

import logging
import threading
import time
from typing import Optional

from databricks import sql as dbsql

from config import DatabricksConfig

logger = logging.getLogger(**name**)

class RoutingTableClient:
“””
Thread-safe Databricks SQL client.
Maintains an in-memory cache of {message_type: landing_path} refreshed
every `cache_ttl_seconds` so the hot polling loop never blocks on SQL.
“””

```
def __init__(self, cfg: DatabricksConfig) -> None:
    self._cfg = cfg
    self._cache: dict[str, str] = {}
    self._cache_lock = threading.Lock()
    self._last_refresh: float = 0.0

    # Eagerly load on construction so the first message is never delayed
    self._refresh_cache()

# ── public API ─────────────────────────────────────────────────────────────

def get_landing_path(self, message_type: str) -> Optional[str]:
    """
    Return the Databricks Volume landing path for `message_type`,
    or None if not found.  Refreshes the cache if TTL has expired.
    """
    self._maybe_refresh()
    with self._cache_lock:
        path = self._cache.get(message_type)

    if path is None:
        logger.warning("No routing entry found for message type '%s'", message_type)
    return path

def force_refresh(self) -> None:
    """Manually invalidate and reload the routing cache."""
    self._refresh_cache()

# ── internal ───────────────────────────────────────────────────────────────

def _maybe_refresh(self) -> None:
    now = time.monotonic()
    if now - self._last_refresh >= self._cfg.cache_ttl_seconds:
        self._refresh_cache()

def _refresh_cache(self) -> None:
    fq_table = (
        f"`{self._cfg.catalog}`"
        f".`{self._cfg.schema}`"
        f".`{self._cfg.routing_table}`"
    )
    query = (
        f"SELECT message_type, landing_path "
        f"FROM {fq_table} "
        f"WHERE is_active = TRUE"
    )
    logger.info("Refreshing routing cache from %s", fq_table)

    try:
        new_cache: dict[str, str] = {}
        with self._open_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
                for row in rows:
                    msg_type   = str(row[0]).strip().upper()
                    landing    = str(row[1]).strip()
                    if not landing.endswith("/"):
                        landing += "/"
                    new_cache[msg_type] = landing

        with self._cache_lock:
            self._cache = new_cache
        self._last_refresh = time.monotonic()
        logger.info("Routing cache loaded: %d entries", len(new_cache))

    except Exception as exc:
        logger.error("Failed to refresh routing cache: %s", exc, exc_info=True)
        # Keep stale cache rather than crashing; next poll will retry

def _open_connection(self):
    """Open a Databricks SQL connection (context manager)."""
    return dbsql.connect(
        server_hostname=self._cfg.host.replace("https://", ""),
        http_path=self._cfg.http_path,
        access_token=self._cfg.token,
    )
```