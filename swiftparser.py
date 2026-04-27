“””
swift_parser.py — Parse raw SWIFT FIN messages and extract MT type + metadata.

Handles both:

- Wrapped format  : {1:…}{2:…}{4:\r\n…\r\n-}
- Raw block 4 text: :20:REF\r\n:23B:CRED\r\n…
  “””

from **future** import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class SwiftMessage:
raw: str                            # original bytes decoded to str
message_type: str                   # e.g. “MT515”
sender_bic: str = “”               # from block 1 / block 2
receiver_bic: str = “”             # from block 2
reference: str = “”                # tag :20: value
fields: dict[str, list[str]] = field(default_factory=dict)  # tag -> [values]

```
@property
def mt_family(self) -> str:
    """Returns e.g. 'MT5' for any MT5xx message."""
    return self.message_type[:3] if len(self.message_type) >= 3 else self.message_type

def is_mt5xx(self) -> bool:
    return self.message_type.startswith("MT5")
```

# ── Parser ────────────────────────────────────────────────────────────────────

class SwiftParseError(ValueError):
“”“Raised when the raw message cannot be parsed into a valid SWIFT structure.”””

class SwiftParser:
“””
Stateless SWIFT FIN parser.  Call SwiftParser.parse(raw_text) -> SwiftMessage.
“””

```
# Block patterns
_BLOCK_RE = re.compile(r"\{(\d):(.*?)\}(?=\{|\Z)", re.DOTALL)
# Application header (block 2): input I<type><dest-bic> or output O<type><time><sender>...
_BLOCK2_INPUT_RE  = re.compile(r"^I(\d{3})([A-Z0-9]{8,11})", re.IGNORECASE)
_BLOCK2_OUTPUT_RE = re.compile(r"^O(\d{3})\d{4}\d{6}([A-Z0-9]{8,11})", re.IGNORECASE)
# Block 1: F01<BIC><seq>
_BLOCK1_RE = re.compile(r"^F\d{2}([A-Z0-9]{8,12})", re.IGNORECASE)
# Field tag inside block 4:  :<tag>: or :<tag><letter>:
_FIELD_RE  = re.compile(r":([0-9]{2}[A-Z]?):(.*?)(?=:[0-9]{2}[A-Z]?:|\Z)", re.DOTALL)

@classmethod
def parse(cls, raw: str) -> SwiftMessage:
    raw = raw.strip()
    if not raw:
        raise SwiftParseError("Empty message")

    blocks = cls._extract_blocks(raw)

    if blocks:
        return cls._parse_wrapped(raw, blocks)
    else:
        # Might be bare block-4 content (no outer braces)
        return cls._parse_bare_block4(raw)

# ── block extraction ───────────────────────────────────────────────────────

@classmethod
def _extract_blocks(cls, raw: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in cls._BLOCK_RE.finditer(raw)}

# ── wrapped {1:..}{2:..}{4:..} format ─────────────────────────────────────

@classmethod
def _parse_wrapped(cls, raw: str, blocks: dict[str, str]) -> SwiftMessage:
    message_type, sender_bic, receiver_bic = cls._extract_header_info(blocks)
    block4 = blocks.get("4", "")
    fields = cls._parse_block4(block4)
    reference = cls._first_field_value(fields, "20")

    return SwiftMessage(
        raw=raw,
        message_type=message_type,
        sender_bic=sender_bic,
        receiver_bic=receiver_bic,
        reference=reference,
        fields=fields,
    )

@classmethod
def _extract_header_info(cls, blocks: dict[str, str]) -> tuple[str, str, str]:
    """Returns (message_type, sender_bic, receiver_bic)."""
    message_type = ""
    sender_bic   = ""
    receiver_bic = ""

    b1 = blocks.get("1", "")
    m1 = cls._BLOCK1_RE.match(b1)
    if m1:
        sender_bic = m1.group(1)

    b2 = blocks.get("2", "")
    mi = cls._BLOCK2_INPUT_RE.match(b2)
    mo = cls._BLOCK2_OUTPUT_RE.match(b2)
    if mi:
        message_type = f"MT{mi.group(1)}"
        receiver_bic = mi.group(2)
    elif mo:
        message_type = f"MT{mo.group(1)}"
        sender_bic   = mo.group(2) or sender_bic
    else:
        # Fallback: first 3 digits in block 2
        digits = re.search(r"(\d{3})", b2)
        if digits:
            message_type = f"MT{digits.group(1)}"

    if not message_type:
        raise SwiftParseError(f"Cannot determine MT type from block 2: '{b2[:60]}'")

    return message_type, sender_bic, receiver_bic

# ── bare block-4 text (no surrounding braces) ─────────────────────────────

@classmethod
def _parse_bare_block4(cls, raw: str) -> SwiftMessage:
    fields = cls._parse_block4(raw)
    # Try to infer type from :12: or message structure
    message_type = ""
    t12 = cls._first_field_value(fields, "12")
    if t12:
        message_type = f"MT{t12.strip()}"
    if not message_type:
        raise SwiftParseError("Cannot determine MT type from bare block-4 content")
    reference = cls._first_field_value(fields, "20")
    return SwiftMessage(raw=raw, message_type=message_type, reference=reference, fields=fields)

# ── block 4 field parsing ──────────────────────────────────────────────────

@classmethod
def _parse_block4(cls, block4: str) -> dict[str, list[str]]:
    # Strip leading/trailing CRLF and trailing "-"
    text = block4.strip().lstrip("\r\n").rstrip("-").strip()
    fields: dict[str, list[str]] = {}
    for m in cls._FIELD_RE.finditer(text):
        tag   = m.group(1)
        value = m.group(2).strip()
        fields.setdefault(tag, []).append(value)
    return fields

@staticmethod
def _first_field_value(fields: dict[str, list[str]], tag: str) -> str:
    vals = fields.get(tag, [])
    return vals[0].split("\n")[0].strip() if vals else ""
```