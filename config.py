“””
config.py — All configuration loaded from environment variables.
IBM MQ SSL uses KDB key repository files whose paths are injected via env vars.
“””

import os
from dataclasses import dataclass, field

# ── IBM MQ ─────────────────────────────────────────────────────────────────────

@dataclass
class MQConfig:
host: str
port: int
queue_manager: str
channel: str
queue_name: str
username: str
password: str

```
# SSL / KDB
ssl_cipher_spec: str        # e.g. "TLS_RSA_WITH_AES_256_CBC_SHA256"
# Path to KDB key repository WITHOUT file extension.
# The library expects <path>.kdb, <path>.sth to exist at this location.
ssl_key_repository: str

# Tuning
poll_interval_seconds: int = 5
get_wait_interval_ms: int = 3_000    # MQGMO_WAIT interval inside a single MQGET call
max_messages_per_poll: int = 100     # safety cap — max messages consumed per poll cycle
max_message_length: int = 4_194_304  # 4 MB MQGET buffer; raise for large SWIFT batches
```

# ── Azure Databricks ───────────────────────────────────────────────────────────

@dataclass
class DatabricksConfig:
host: str           # e.g. “https://adb-<workspace-id>.azuredatabricks.net”
token: str          # PAT or service-principal token
http_path: str      # SQL warehouse HTTP path
catalog: str        # Unity Catalog name
schema: str         # Schema holding the routing table
routing_table: str  # Table name, e.g. “swift_message_routing”
cache_ttl_seconds: int = 300   # how long to cache routing table locally

# ── Composite ─────────────────────────────────────────────────────────────────

@dataclass
class Config:
mq: MQConfig
databricks: DatabricksConfig

```
@classmethod
def from_env(cls) -> "Config":
    def _req(key: str) -> str:
        val = os.environ.get(key, "").strip()
        if not val:
            raise EnvironmentError(f"Required environment variable '{key}' is not set.")
        return val

    def _opt(key: str, default: str = "") -> str:
        return os.environ.get(key, default).strip()

    mq = MQConfig(
        host=_req("MQ_HOST"),
        port=int(_req("MQ_PORT")),
        queue_manager=_req("MQ_QUEUE_MANAGER"),
        channel=_req("MQ_CHANNEL"),
        queue_name=_req("MQ_QUEUE_NAME"),
        username=_req("MQ_USERNAME"),
        password=_req("MQ_PASSWORD"),
        ssl_cipher_spec=_req("MQ_SSL_CIPHER_SPEC"),
        ssl_key_repository=_req("MQ_SSL_KEY_REPOSITORY"),  # e.g. /mnt/mq-ssl/clientkey
        poll_interval_seconds=int(_opt("MQ_POLL_INTERVAL_SECONDS", "5")),
        get_wait_interval_ms=int(_opt("MQ_GET_WAIT_INTERVAL_MS", "3000")),
        max_messages_per_poll=int(_opt("MQ_MAX_MESSAGES_PER_POLL", "100")),
        max_message_length=int(_opt("MQ_MAX_MESSAGE_LENGTH", str(4 * 1024 * 1024))),
    )

    databricks = DatabricksConfig(
        host=_req("DATABRICKS_HOST"),
        token=_req("DATABRICKS_TOKEN"),
        http_path=_req("DATABRICKS_HTTP_PATH"),
        catalog=_req("DATABRICKS_CATALOG"),
        schema=_req("DATABRICKS_SCHEMA"),
        routing_table=_opt("DATABRICKS_ROUTING_TABLE", "swift_message_routing"),
        cache_ttl_seconds=int(_opt("DATABRICKS_CACHE_TTL_SECONDS", "300")),
    )

    return cls(mq=mq, databricks=databricks)
```