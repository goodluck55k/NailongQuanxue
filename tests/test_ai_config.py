import pytest

from app import ai_config, secure_credentials
from app.ai_config import (AiConfigError, AiSettings, CredentialStorageError, PROTOCOLS,
                           clean_base_url, clean_key, clean_model, clean_protocol,
                           clear_settings, migrate_plain_key, read_settings, save_settings,
                           validate)
from app.config_store import ConfigStore


@pytest.mark.parametrize("value", ["", "   ", "api.example.com", "ftp://x.test", "https://",
                                   "https://a b.test", "https://api.test/v1?key=1",
                                   "https://api.test/v1#frag"])
def test_base_url_rejects_unusable_text(value):
    with pytest.raises(AiConfigError):
        clean_base_url(value)


def test_base_url_trims_whitespace_and_trailing_slash():
    assert clean_base_url(" https://api.example.com/v1/ ") == "https://api.example.com/v1"


def test_protocol_model_and_key_normalisation():
    assert clean_protocol(" Gemini ") == "gemini"
    with pytest.raises(AiConfigError):
        clean_protocol("openrouter")
    assert clean_model("  qwen-vl-max ") == "qwen-vl-max"
    with pytest.raises(AiConfigError):
        clean_model("two words")
    with pytest.raises(AiConfigError):
        clean_model("x" * 201)
    assert clean_key("Bearer sk-abc") == "sk-abc"
    with pytest.raises(AiConfigError):
        clean_key("bad\nkey")


def test_settings_display_text_never_leaks_the_key():
    empty = AiSettings()
    assert not empty.configured
    assert "未配置" in empty.status_text()
    assert empty.masked_key() == "未填写（本地服务可留空）"
    full = AiSettings(base_url="https://api.example.com/v1", api_key="sk-1234567890",
                      model="vision-1", verified=True)
    assert full.configured and full.host == "api.example.com"
    text = full.status_text()
    assert "api.example.com" in text and "vision-1" in text and "已验证" in text
    assert "sk-1234567890" not in text
    assert full.masked_key() == "sk-…7890"
    assert AiSettings(api_key="short").masked_key() == "••••••"


def test_read_settings_tolerates_garbage():
    assert read_settings({}).configured is False
    assert read_settings({"ai": "not-a-dict"}).protocol == "openai"
    settings = read_settings({"ai": {"protocol": "unknown", "base_url": 5, "model": None,
                                     "verified": "yes"}})
    assert settings.protocol == "openai"
    assert settings.base_url == "" and settings.model == ""
    assert settings.verified is False


def test_validate_and_persist_round_trip(tmp_path):
    store = ConfigStore(tmp_path)
    with pytest.raises(AiConfigError):
        save_settings(store, AiSettings(base_url="https://api.test", model=""))
    saved = save_settings(store, AiSettings(protocol="anthropic",
                                            base_url="https://api.anthropic.test/v1/",
                                            api_key="sk-key", model="claude-vision"))
    assert saved.base_url == "https://api.anthropic.test/v1"
    assert saved.verified is False
    again = read_settings(ConfigStore(tmp_path).values)
    assert again == saved
    assert again.protocol in PROTOCOLS
    verified = save_settings(store, again, verified=True)
    assert verified.verified and verified.verified_at
    assert read_settings(ConfigStore(tmp_path).values).verified is True
    clear_settings(store)
    assert read_settings(ConfigStore(tmp_path).values).configured is False


def test_validate_keeps_verification_flag():
    normalized = validate(AiSettings(base_url="https://api.test", model="m", verified=True,
                                     verified_at="2026-11-01T10:00:00+08:00"))
    assert normalized.verified is True
    assert normalized.verified_at == "2026-11-01T10:00:00+08:00"

def test_key_is_never_written_in_plain_text_when_dpapi_is_unavailable(tmp_path, monkeypatch):
    store = ConfigStore(tmp_path)
    save_settings(store, AiSettings(base_url="https://api.test", api_key="sk-old", model="m"))
    before = (tmp_path / "settings.json").read_bytes()

    monkeypatch.setattr(secure_credentials, "available", lambda: False)
    with pytest.raises(CredentialStorageError) as error:
        save_settings(store, AiSettings(base_url="https://api.test", api_key="sk-new", model="m2"))

    assert "明文" in str(error.value) and "DPAPI" in str(error.value)
    assert (tmp_path / "settings.json").read_bytes() == before
    assert read_settings(ConfigStore(tmp_path).values).api_key == "sk-old"


def test_sealing_failure_is_reported_instead_of_falling_back_to_plain_text(tmp_path, monkeypatch):
    store = ConfigStore(tmp_path)
    monkeypatch.setattr(secure_credentials, "available", lambda: True)
    monkeypatch.setattr(secure_credentials, "protect", lambda text: "")

    with pytest.raises(CredentialStorageError):
        ai_config.payload(AiSettings(base_url="https://api.test", api_key="sk-secret", model="m"))
    assert not (tmp_path / "settings.json").exists()


def test_migration_leaves_a_plain_text_key_alone_when_it_cannot_seal(tmp_path, monkeypatch):
    store = ConfigStore(tmp_path)
    store.save(ai={"protocol": "openai", "base_url": "https://api.test", "api_key": "sk-legacy",
                   "api_key_sealed": "", "model": "m", "verified": True, "verified_at": ""})
    before = (tmp_path / "settings.json").read_bytes()

    monkeypatch.setattr(secure_credentials, "available", lambda: False)

    assert migrate_plain_key(store) is False
    assert (tmp_path / "settings.json").read_bytes() == before
    assert read_settings(ConfigStore(tmp_path).values).api_key == "sk-legacy"