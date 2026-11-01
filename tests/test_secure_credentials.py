import json
import sys

import pytest

from app import secure_credentials
from app.ai_config import (AiSettings, legacy_key_present, migrate_plain_key, payload,
                           read_settings, save_settings)
from app.config_store import ConfigStore

windows_only = pytest.mark.skipif(sys.platform != "win32" or not secure_credentials.available(),
                                  reason="Windows DPAPI is required for sealed credentials")


@windows_only
def test_sealed_value_round_trips_and_hides_plaintext():
    sealed = secure_credentials.protect("sk-live-1234567890")
    assert secure_credentials.is_sealed(sealed)
    assert "sk-live-1234567890" not in sealed
    assert secure_credentials.unprotect(sealed) == "sk-live-1234567890"


@windows_only
def test_sealed_blob_is_not_portable_plain_text():
    sealed = secure_credentials.protect("sk-live-1234567890")
    raw = sealed[len(secure_credentials.PREFIX):]
    assert "sk-live" not in raw


def test_plain_text_passthrough_and_garbage():
    assert secure_credentials.unprotect("sk-legacy") == "sk-legacy"
    assert secure_credentials.unprotect("") == ""
    assert secure_credentials.unprotect(None) == ""
    assert secure_credentials.unprotect("dpapi:not-base64!!") == ""
    assert secure_credentials.unprotect("dpapi:") == ""
    assert secure_credentials.is_sealed("dpapi:abc") is True
    assert secure_credentials.is_sealed("plain") is False


@windows_only
def test_settings_file_never_contains_the_raw_key(tmp_path):
    store = ConfigStore(tmp_path)
    save_settings(store, AiSettings(base_url="https://api.example.com/v1",
                                    api_key="sk-secret-value", model="vision-1"))
    text = (tmp_path / "settings.json").read_text(encoding="utf-8")
    assert "sk-secret-value" not in text
    stored = json.loads(text)["ai"]
    assert stored["api_key"] == ""
    assert secure_credentials.is_sealed(stored["api_key_sealed"])
    assert read_settings(ConfigStore(tmp_path).values).api_key == "sk-secret-value"


@windows_only
def test_legacy_plaintext_key_is_resealed_once(tmp_path):
    store = ConfigStore(tmp_path)
    store.save(ai={"protocol": "openai", "base_url": "https://api.example.com/v1",
                   "api_key": "sk-old-key", "model": "vision-1", "verified": True,
                   "verified_at": "2026-11-01T10:00:00+08:00"})
    assert legacy_key_present(store.values) is True
    assert read_settings(store.values).api_key == "sk-old-key"
    assert migrate_plain_key(store) is True
    text = (tmp_path / "settings.json").read_text(encoding="utf-8")
    assert "sk-old-key" not in text
    again = read_settings(ConfigStore(tmp_path).values)
    assert again.api_key == "sk-old-key" and again.verified is True
    assert legacy_key_present(ConfigStore(tmp_path).values) is False
    assert migrate_plain_key(store) is False


def test_payload_shape_stays_backward_compatible():
    """Readers of an unsealed file (older builds) still find an ``api_key`` field."""
    written = payload(AiSettings(base_url="https://api.example.com/v1", api_key="sk-x",
                                 model="m"))
    assert set(written) == {"protocol", "base_url", "api_key", "api_key_sealed",
                            "model", "verified", "verified_at"}
    if secure_credentials.available():
        assert written["api_key"] == ""
    else:
        assert written["api_key"] == "sk-x"
