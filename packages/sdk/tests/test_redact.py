"""Tests for glasspipe.redact — pattern library, detect(), redact(), redact_trace()."""
import json
import os

import pytest

from glasspipe.redact import detect, redact, redact_trace


# ---------------------------------------------------------------------------
# detect() — one test per pattern type
# ---------------------------------------------------------------------------

def test_detect_openai_key():
    hits = detect("my key is sk-abcdefghijklmnopqrstuvwxyz123456")
    types = [h["type"] for h in hits]
    assert "openai_key" in types


def test_detect_anthropic_key():
    hits = detect("token: sk-ant-abcdefghijklmnopqrstuvwxyz-ABCDEFG1234")
    types = [h["type"] for h in hits]
    assert "anthropic_key" in types


def test_detect_aws_access_key():
    hits = detect("access key AKIAIOSFODNN7EXAMPLE123 here")
    types = [h["type"] for h in hits]
    assert "aws_access_key" in types


def test_detect_github_token():
    hits = detect("token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk")
    types = [h["type"] for h in hits]
    assert "github_token" in types


def test_detect_jwt():
    token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyMTIzIn0.SomeSignatureHere"
    hits = detect(token)
    types = [h["type"] for h in hits]
    assert "jwt" in types


def test_detect_email():
    hits = detect("contact us at hello@example.com for support")
    types = [h["type"] for h in hits]
    assert "email" in types


def test_detect_credit_card():
    hits = detect("card number 4111 1111 1111 1111 was used")
    types = [h["type"] for h in hits]
    assert "credit_card" in types


def test_detect_phone_us():
    hits = detect("call me at (555) 867-5309 anytime")
    types = [h["type"] for h in hits]
    assert "phone_us" in types


def test_detect_url_with_query():
    hits = detect("fetched https://api.example.com/search?q=secret&token=abc")
    types = [h["type"] for h in hits]
    assert "url_with_query" in types


# ---------------------------------------------------------------------------
# redact() behaviour
# ---------------------------------------------------------------------------

def test_clean_string_passes_through():
    result = redact("hello world, no secrets here")
    assert result == "hello world, no secrets here"


def test_nested_dict_redacted():
    data = {
        "user": "alice",
        "contact": {"email": "alice@example.com", "note": "nothing sensitive"},
        "tags": ["ok", "safe"],
    }
    result = redact(data)
    # email inside nested dict must be redacted
    assert "[REDACTED:email]" in result["contact"]["email"]
    # clean values pass through
    assert result["user"] == "alice"
    assert result["contact"]["note"] == "nothing sensitive"
    assert result["tags"] == ["ok", "safe"]


def test_custom_pattern_via_argument():
    result = redact(
        "my internal id is INT-99887766",
        custom_patterns={"internal_id": r"INT-\d{8}"},
    )
    assert "[REDACTED:internal_id]" in result


def test_env_var_custom_pattern(monkeypatch):
    monkeypatch.setenv(
        "GLASSPIPE_REDACT_PATTERNS",
        json.dumps({"corp_secret": r"CORP-[A-Z]{4}-\d{4}"}),
    )
    result = redact("credential CORP-ABCD-1234 found")
    assert "[REDACTED:corp_secret]" in result
