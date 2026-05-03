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


def test_detect_openai_key_proj():
    hits = detect("sk-proj-FAKE-SECRET-KEY-DO-NOT-SHARE-9c8d7e6f")
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


def test_detect_bearer_token():
    hits = detect("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc.def")
    types = [h["type"] for h in hits]
    assert "bearer_token" in types


def test_detect_us_ssn():
    hits = detect("ssn is 123-45-6789 on file")
    types = [h["type"] for h in hits]
    assert "us_ssn" in types


def test_detect_credential_password_quote():
    hits = detect("password 'hunter2SuperSecret!'")
    types = [h["type"] for h in hits]
    assert "credential" in types


def test_detect_credential_api_key_equals():
    hits = detect("api_key=sk-abc123longkeyvaluehere")
    types = [h["type"] for h in hits]
    assert "credential" in types


def test_detect_credential_secret_colon():
    hits = detect('secret: "my-super-secret-value"')
    types = [h["type"] for h in hits]
    assert "credential" in types


def test_detect_sensitive_param():
    hits = detect("https://api.example.com/v1/chat?api_key=sk-abc123longkeyvalue")
    types = [h["type"] for h in hits]
    assert "sensitive_param" in types


def test_detect_sensitive_param_token():
    hits = detect("https://api.example.com/search?token=abc123")
    types = [h["type"] for h in hits]
    assert "sensitive_param" in types


def test_no_detect_benign_query_param():
    hits = detect("https://api.openai.com/v1/chat?version=2024-01")
    types = [h["type"] for h in hits]
    assert "sensitive_param" not in types


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


# ---------------------------------------------------------------------------
# Smoketest: all 5 user-reported secret types must be detected
# ---------------------------------------------------------------------------

def test_smoketest_all_five_secrets():
    text = (
        "email: user@example.com, "
        "card: 4532-1488-0343-6467, "
        "key: sk-proj-FAKE-SECRET-KEY-DO-NOT-SHARE-9c8d7e6f, "
        "ssn: 123-45-6789, "
        "password 'hunter2SuperSecret!'"
    )
    hits = detect(text)
    types = [h["type"] for h in hits]
    assert "email" in types, "email not detected"
    assert "credit_card" in types, "credit_card not detected"
    assert "openai_key" in types, "openai_key not detected"
    assert "us_ssn" in types, "us_ssn not detected"
    assert "credential" in types, "credential (password proximity) not detected"


def test_smoketest_redact_all_five_secrets():
    data = {
        "email": "user@example.com",
        "card": "4532-1488-0343-6467",
        "api_key": "sk-proj-FAKE-SECRET-KEY-DO-NOT-SHARE-9c8d7e6f",
        "ssn": "123-45-6789",
        "note": "password 'hunter2SuperSecret!'",
    }
    result = redact(data)
    result_str = json.dumps(result)
    assert "[REDACTED:email]" in result_str
    assert "[REDACTED:credit_card]" in result_str
    assert "[REDACTED:openai_key]" in result_str
    assert "[REDACTED:us_ssn]" in result_str
    assert "[REDACTED:credential]" in result_str
    assert "user@example.com" not in result_str
    assert "4532-1488-0343-6467" not in result_str
    assert "sk-proj-FAKE" not in result_str
    assert "123-45-6789" not in result_str
    assert "hunter2SuperSecret" not in result_str
