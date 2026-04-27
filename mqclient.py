“””
mq_client.py — IBM MQ connection + message consumer.

Uses the OFFICIAL `ibm_mq` Python library (pip install ibm-mq).
The library exposes the raw MQI via:
ibm_mq.mqi          — MQCONNX, MQOPEN, MQGET, MQCLOSE, MQDISC
ibm_mq.mqi.CMQC     — All MQ constants (MQRC_*, MQGMO_*, MQOO_*, etc.)
ibm_mq.mqi.structures — MQCD, MQSCO, MQCNO, MQMD, MQGMO structs

SSL is configured via an MQSCO struct pointing at the KDB key-repository.
KDB files are mounted into the AKS pod as a Kubernetes Secret volume.

Expected files on disk (path prefix from MQ_SSL_KEY_REPOSITORY env var):
<MQ_SSL_KEY_REPOSITORY>.kdb   — Key Database
<MQ_SSL_KEY_REPOSITORY>.sth   — Stash file (password-protected)

Connection flow:
MQClient.**enter**  → MQCONNX (with MQCD + MQSCO + MQCNO) + MQOPEN
MQClient.get_messages() → generator: MQGET loop until MQRC_NO_MSG_AVAILABLE
MQClient.**exit**   → MQCLOSE + MQDISC
“””

from **future** import annotations

import logging
import time
from typing import Generator, Optional, Tuple

import ibm_mq.mqi as mqi
from ibm_mq.mqi import CMQC
from ibm_mq.mqi.structures import MQCD, MQCNO, MQGMO, MQMD, MQSCO, MQOD

from config import MQConfig

logger = logging.getLogger(**name**)

# ibm_mq uses integer handles; 0 / negative means “not connected”

_NULL_HANDLE = mqi.MQHC_UNUSABLE_HCONN

# Type alias: raw message bytes + MQMD descriptor

MsgData = Tuple[bytes, MQMD]

class MQConnectionError(RuntimeError):
pass

class MQClient:
“””
Context-manager wrapper around a single IBM MQ queue consumer
using the official ibm_mq library.

```
Usage:
    with MQClient(cfg) as client:
        for raw_bytes, md in client.get_messages():
            process(raw_bytes)
"""

def __init__(self, cfg: MQConfig) -> None:
    self._cfg = cfg
    self._hconn: int = _NULL_HANDLE   # connection handle from MQCONNX
    self._hobj:  int = _NULL_HANDLE   # object (queue) handle from MQOPEN

# ── Context manager ────────────────────────────────────────────────────────

def __enter__(self) -> "MQClient":
    self._connect()
    return self

def __exit__(self, *_) -> None:
    self._disconnect()

# ── Public API ─────────────────────────────────────────────────────────────

def get_messages(self) -> Generator[MsgData, None, None]:
    """
    Drain the queue, yielding (raw_bytes, MQMD) for each message
    until the queue is empty (MQRC_NO_MSG_AVAILABLE).

    Auto-reconnects on connection-broken / QM-quiescing errors and
    stops the current cycle so the caller's loop can retry.
    """
    if self._hobj == _NULL_HANDLE:
        raise MQConnectionError("MQClient is not connected — use as a context manager")

    # ── Build MQGMO once, reuse per get ───────────────────────────────────
    gmo = MQGMO()
    gmo.Options = (
        CMQC.MQGMO_WAIT              # block up to WaitInterval before returning
        | CMQC.MQGMO_FAIL_IF_QUIESCING  # surface QM shutdown immediately
        | CMQC.MQGMO_CONVERT         # ask MQ to convert EBCDIC → client codepage
    )
    gmo.WaitInterval = self._cfg.get_wait_interval_ms

    count = 0
    while count < self._cfg.max_messages_per_poll:
        md = MQMD()                  # fresh descriptor per message
        try:
            msg_bytes: bytes = mqi.MQGET(
                self._hconn,
                self._hobj,
                md,
                gmo,
                self._cfg.max_message_length,
            )
            count += 1
            logger.debug(
                "MQGET #%d  MsgId=%s  Format=%s  Len=%d",
                count,
                bytes(md.MsgId).hex(),
                bytes(md.Format).rstrip(b"\x00 ").decode(errors="replace"),
                len(msg_bytes),
            )
            yield msg_bytes, md

        except mqi.MQMIError as err:
            reason = err.reason

            if reason == CMQC.MQRC_NO_MSG_AVAILABLE:
                logger.debug("Queue empty after %d message(s)", count)
                break

            elif reason in (
                CMQC.MQRC_CONNECTION_BROKEN,
                CMQC.MQRC_Q_MGR_NOT_AVAILABLE,
                CMQC.MQRC_Q_MGR_QUIESCING,
            ):
                logger.warning(
                    "MQ connection lost (MQRC %d). Will reconnect on next poll.", reason
                )
                self._reconnect()
                break   # let the outer poll loop sleep and retry

            elif reason == CMQC.MQRC_TRUNCATED_MSG_FAILED:
                # Message was larger than max_message_length — log and skip
                logger.error(
                    "Message truncated (MQRC 2027) — increase MQ_MAX_MESSAGE_LENGTH. "
                    "Message skipped."
                )
                # Destructively get to discard the oversized message
                gmo_skip = MQGMO()
                gmo_skip.Options = CMQC.MQGMO_ACCEPT_TRUNCATED_MSG
                try:
                    mqi.MQGET(self._hconn, self._hobj, MQMD(), gmo_skip, 0)
                except mqi.MQMIError:
                    pass

            else:
                logger.error(
                    "MQGET error: CompCode=%d Reason=%d", err.comp, reason
                )
                raise

# ── Internal ───────────────────────────────────────────────────────────────

def _connect(self) -> None:
    cfg = self._cfg
    logger.info(
        "Connecting to IBM MQ  host=%s:%d  qm=%s  channel=%s  queue=%s",
        cfg.host, cfg.port, cfg.queue_manager, cfg.channel, cfg.queue_name,
    )

    # ── MQCD — Client Channel Definition ──────────────────────────────────
    cd = MQCD()
    cd.ChannelName    = cfg.channel.encode()
    cd.ConnectionName = f"{cfg.host}({cfg.port})".encode()
    cd.ChannelType    = CMQC.MQCHT_CLNTCONN
    cd.TransportType  = CMQC.MQXPT_TCP
    cd.SSLCipherSpec  = cfg.ssl_cipher_spec.encode()

    # ── MQSCO — SSL Configuration Options (points at KDB key repo) ────────
    sco = MQSCO()
    # KeyRepository must be the path WITHOUT the file extension.
    # ibm_mq will find  <path>.kdb  and  <path>.sth  automatically.
    sco.KeyRepository = cfg.ssl_key_repository.encode()

    # ── MQCNO — Connection Options ─────────────────────────────────────────
    cno = MQCNO()
    cno.Options   = CMQC.MQCNO_CLIENT_BINDING   # force client (not local) connection
    cno.ClientConn = cd
    cno.SSLConfig  = sco

    try:
        self._hconn = mqi.MQCONNX(
            cfg.queue_manager,
            cno,
            user=cfg.username,
            password=cfg.password,
        )
    except mqi.MQMIError as err:
        raise MQConnectionError(
            f"MQCONNX failed for queue manager '{cfg.queue_manager}': "
            f"CompCode={err.comp} Reason={err.reason}"
        ) from err

    # ── MQOPEN — Open the input queue ──────────────────────────────────────
    od = MQOD()
    od.ObjectName = cfg.queue_name.encode()
    od.ObjectType = CMQC.MQOT_Q

    open_opts = CMQC.MQOO_INPUT_AS_Q_DEF | CMQC.MQOO_FAIL_IF_QUIESCING

    try:
        self._hobj = mqi.MQOPEN(self._hconn, od, open_opts)
    except mqi.MQMIError as err:
        # Disconnect cleanly before raising
        try:
            mqi.MQDISC(self._hconn)
        except Exception:
            pass
        self._hconn = _NULL_HANDLE
        raise MQConnectionError(
            f"MQOPEN failed for queue '{cfg.queue_name}': "
            f"CompCode={err.comp} Reason={err.reason}"
        ) from err

    logger.info("IBM MQ connection established  hconn=%d  hobj=%d", self._hconn, self._hobj)

def _disconnect(self) -> None:
    # MQCLOSE
    if self._hobj != _NULL_HANDLE:
        try:
            mqi.MQCLOSE(self._hconn, self._hobj, CMQC.MQCO_NONE)
            logger.debug("MQCLOSE OK")
        except mqi.MQMIError as err:
            logger.warning("MQCLOSE warning: CompCode=%d Reason=%d", err.comp, err.reason)
        finally:
            self._hobj = _NULL_HANDLE

    # MQDISC
    if self._hconn != _NULL_HANDLE:
        try:
            mqi.MQDISC(self._hconn)
            logger.info("MQDISC OK — disconnected from IBM MQ")
        except mqi.MQMIError as err:
            logger.warning("MQDISC warning: CompCode=%d Reason=%d", err.comp, err.reason)
        finally:
            self._hconn = _NULL_HANDLE

def _reconnect(self, retries: int = 5, backoff_seconds: float = 3.0) -> None:
    self._disconnect()
    for attempt in range(1, retries + 1):
        try:
            logger.info("Reconnect attempt %d/%d ...", attempt, retries)
            self._connect()
            logger.info("Reconnected successfully on attempt %d", attempt)
            return
        except MQConnectionError as err:
            logger.warning("Reconnect attempt %d failed: %s", attempt, err)
            if attempt < retries:
                time.sleep(backoff_seconds * attempt)
    raise MQConnectionError(f"IBM MQ reconnect failed after {retries} attempts")
```