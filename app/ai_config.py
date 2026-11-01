"""User-supplied vision API settings: validation, persistence and display text.

The key is sealed with Windows DPAPI before it reaches the settings file, is
never logged, and is never shown in full by the interface. Everything here is
Qt-free so it can be tested without a GUI.
"""
from dataclasses import dataclass, replace
from datetime import datetime
from urllib.parse import urlsplit

from . import secure_credentials

PROTOCOLS = {
    "openai": "OpenAI 兼容（/chat/completions）",
    "anthropic": "Anthropic Messages（/v1/messages）",
    "gemini": "Google Gemini（generateContent）",
}
PROTOCOL_ORDER = ("openai", "anthropic", "gemini")
MAX_URL = 400
MAX_MODEL = 200
MAX_KEY = 8192


class AiConfigError(ValueError):
    """Unusable configuration text; the message is safe to show to the user."""


def clean_protocol(value):
    text = str(value or "").strip().lower()
    if text not in PROTOCOLS:
        raise AiConfigError("请选择接口协议类型")
    return text


def clean_base_url(value):
    text = str(value or "").strip()
    if not text:
        raise AiConfigError("请填写 API Base URL，例如 https://api.example.com/v1")
    if len(text) > MAX_URL:
        raise AiConfigError("Base URL 过长")
    if any(character.isspace() for character in text):
        raise AiConfigError("Base URL 不能包含空格或换行")
    parts = urlsplit(text)
    if parts.scheme.lower() not in ("http", "https"):
        raise AiConfigError("Base URL 必须以 http:// 或 https:// 开头")
    if not parts.hostname:
        raise AiConfigError("Base URL 缺少主机名")
    if parts.query or parts.fragment:
        raise AiConfigError("Base URL 不能包含 ? 查询参数或 # 锚点")
    return text.rstrip("/")


def clean_model(value):
    text = str(value or "").strip()
    if not text:
        raise AiConfigError("请填写支持图像输入的模型 ID")
    if len(text) > MAX_MODEL or any(character.isspace() for character in text):
        raise AiConfigError("模型 ID 不能包含空格，且不超过 200 个字符")
    return text


def clean_key(value):
    text = str(value or "").strip()
    if text.lower().startswith("bearer "):
        text = text[7:].strip()
    if len(text) > MAX_KEY or "\r" in text or "\n" in text:
        raise AiConfigError("API Key 不合法")
    return text


@dataclass(frozen=True)
class AiSettings:
    protocol: str = "openai"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    verified: bool = False
    verified_at: str = ""

    @property
    def configured(self):
        return bool(self.base_url and self.model and self.protocol in PROTOCOLS)

    @property
    def host(self):
        try:
            return urlsplit(self.base_url).hostname or self.base_url
        except ValueError:
            return self.base_url

    def status_text(self):
        if not self.configured:
            return "AI 接入：未配置 · 无法通过动作挑战解除限制"
        state = "已验证" if self.verified else "尚未验证"
        return f"AI 接入：{self.host} · {self.model} · {state}"

    def masked_key(self):
        if not self.api_key:
            return "未填写（本地服务可留空）"
        if len(self.api_key) <= 8:
            return "••••••"
        return f"{self.api_key[:3]}…{self.api_key[-4:]}"

    def changed(self, **changes):
        return replace(self, **changes)


def read_settings(values):
    """Tolerant read: garbage in the settings file never raises here."""
    raw = values.get("ai") if isinstance(values, dict) else None
    raw = raw if isinstance(raw, dict) else {}

    def text(name):
        value = raw.get(name)
        return value if isinstance(value, str) else ""

    protocol = raw.get("protocol")
    sealed = text("api_key_sealed")
    key = secure_credentials.unprotect(sealed) if sealed else text("api_key").strip()
    return AiSettings(
        protocol=protocol if protocol in PROTOCOLS else "openai",
        base_url=text("base_url").strip().rstrip("/"),
        api_key=key,
        model=text("model").strip(),
        verified=raw.get("verified") is True,
        verified_at=text("verified_at"),
    )


def legacy_key_present(values):
    """True when the settings file still holds an unsealed key from an older build."""
    raw = values.get("ai") if isinstance(values, dict) else None
    if not isinstance(raw, dict):
        return False
    plain = raw.get("api_key")
    return isinstance(plain, str) and bool(plain.strip()) and not secure_credentials.is_sealed(raw.get("api_key_sealed"))


def validate(settings):
    """Raise AiConfigError with a user-facing message, or return normalized values."""
    return AiSettings(protocol=clean_protocol(settings.protocol),
                      base_url=clean_base_url(settings.base_url),
                      api_key=clean_key(settings.api_key),
                      model=clean_model(settings.model),
                      verified=bool(settings.verified),
                      verified_at=settings.verified_at)


def payload(settings):
    """Settings written to disk: the key is DPAPI-sealed, never plain."""
    sealed = secure_credentials.protect(settings.api_key)
    if sealed:
        key_fields = {"api_key": "", "api_key_sealed": sealed}
    else:
        key_fields = {"api_key": settings.api_key, "api_key_sealed": ""}
    return {"protocol": settings.protocol, "base_url": settings.base_url,
            **key_fields, "model": settings.model,
            "verified": bool(settings.verified), "verified_at": settings.verified_at}


def save_settings(store, settings, verified=None):
    """Persist normalized settings through ConfigStore; returns what was written."""
    normalized = validate(settings)
    if verified is not None:
        normalized = replace(normalized, verified=bool(verified),
                             verified_at=datetime.now().astimezone().isoformat(timespec="seconds")
                             if verified else "")
    store.save(ai=payload(normalized))
    return normalized


def mark_verified(store, settings):
    return save_settings(store, settings, verified=True)


def clear_settings(store):
    store.save(ai={"protocol": "openai", "base_url": "", "api_key": "", "api_key_sealed": "",
                   "model": "", "verified": False, "verified_at": ""})


def migrate_plain_key(store):
    """Re-seal a key written by an older build (plain text in settings.json)."""
    if not legacy_key_present(store.values):
        return False
    try:
        settings = read_settings(store.values)
    except Exception:
        return False
    if not settings.api_key:
        return False
    save_settings(store, settings, verified=settings.verified)
    return True
