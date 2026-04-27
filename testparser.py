“””
tests/test_swift_parser.py — Unit tests for SWIFT message parsing.
Run with:  pytest tests/
“””

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(**file**), “..”, “src”))

import pytest
from swift_parser import SwiftParser, SwiftParseError, SwiftMessage

# ── Sample messages ────────────────────────────────────────────────────────────

MT515_WRAPPED = (
“{1:F01BANKBEBBAXXX0000000000}”
“{2:I515BANKDEBBXXXXN}”
“{4:\r\n”
“:20:SWIFT-TEST-001\r\n”
“:23G:NEWM\r\n”
“:98A::SETT//20240615\r\n”
“:35B:ISIN US0231351067\r\n”
“:36B::SETT//FAMT/100000,\r\n”
“-}”
)

MT502_WRAPPED = (
“{1:F01BANKUSNYAXXX0000000000}”
“{2:I502BANKGB2LXXXXN}”
“{4:\r\n”
“:20:REF20240101\r\n”
“:23G:NEWM\r\n”
“-}”
)

MT999_WRAPPED = (
“{1:F01BANKBEBBAXXX0000000000}”
“{2:I999BANKDEBBXXXXN}”
“{4:\r\n”
“:20:FREE-TEXT-001\r\n”
“:79:Some free format text\r\n”
“-}”
)

# ── Tests ──────────────────────────────────────────────────────────────────────

class TestSwiftParser:

```
def test_mt515_type_detected(self):
    msg = SwiftParser.parse(MT515_WRAPPED)
    assert msg.message_type == "MT515"

def test_mt515_is_mt5xx(self):
    msg = SwiftParser.parse(MT515_WRAPPED)
    assert msg.is_mt5xx() is True

def test_mt515_sender_bic(self):
    msg = SwiftParser.parse(MT515_WRAPPED)
    assert "BANKBEBB" in msg.sender_bic

def test_mt515_reference(self):
    msg = SwiftParser.parse(MT515_WRAPPED)
    assert msg.reference == "SWIFT-TEST-001"

def test_mt515_fields_parsed(self):
    msg = SwiftParser.parse(MT515_WRAPPED)
    assert "20" in msg.fields
    assert "23G" in msg.fields

def test_mt502_type(self):
    msg = SwiftParser.parse(MT502_WRAPPED)
    assert msg.message_type == "MT502"
    assert msg.is_mt5xx() is True

def test_mt999_not_mt5xx(self):
    msg = SwiftParser.parse(MT999_WRAPPED)
    assert msg.message_type == "MT999"
    assert msg.is_mt5xx() is False

def test_mt_family(self):
    msg = SwiftParser.parse(MT515_WRAPPED)
    assert msg.mt_family == "MT5"

def test_empty_message_raises(self):
    with pytest.raises(SwiftParseError):
        SwiftParser.parse("")

def test_no_block2_raises(self):
    with pytest.raises(SwiftParseError):
        SwiftParser.parse("{1:F01BANKBEBBAXXX0000000000}{4:\r\n:20:REF\r\n-}")

def test_raw_preserved(self):
    msg = SwiftParser.parse(MT515_WRAPPED)
    assert "SWIFT-TEST-001" in msg.raw
```

class TestFileNaming:
“”“Test the filename builder via DatabricksFileWriter internals.”””

```
def test_filename_contains_type_and_ref(self):
    from file_writer import DatabricksFileWriter
    msg = SwiftParser.parse(MT515_WRAPPED)
    raw = MT515_WRAPPED.encode()
    name = DatabricksFileWriter._build_filename(msg, raw)
    assert "MT515" in name
    assert "SWIFT-TEST-001" in name
    assert name.endswith(".txt")

def test_filename_no_special_chars(self):
    from file_writer import DatabricksFileWriter
    msg = SwiftParser.parse(MT515_WRAPPED)
    raw = MT515_WRAPPED.encode()
    name = DatabricksFileWriter._build_filename(msg, raw)
    # Only alphanumeric, underscore, hyphen, dot allowed
    import re
    assert re.match(r'^[\w\-\.]+$', name), f"Bad filename: {name}"
```