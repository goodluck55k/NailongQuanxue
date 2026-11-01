"""Minimal HTTPS client for a user-configured image-capable model.

Standard library only (no new dependency, no bundled SDK) so the Windows build
stays reproducible. The provider is never assumed: the endpoint, protocol,
model and credentials are always taken from the user's configuration, and a
reply that cannot be validated is treated as a technical failure — never as a
pass.
"""
import base64
import json
import socket
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import quote

from .ai_config import AiSettings

REQUEST_TIMEOUT = 45
MAX_RESPONSE_BYTES = 1_048_576
MAX_IMAGES = 10
SYSTEM_PROMPT = (
    "你是严格的录像动作核验员。你只依据画面中可见的身体姿态作判断，"
    "不依据文字描述、不推测用户意图、不因为用户声称完成而放行。"
)


class VisionError(Exception):
    """A technical failure: the challenge must not be treated as passed."""

    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind
        self.detail = message

    def user_message(self):
        prefix = {
            "config": "AI 配置不完整",
            "network": "无法连接 AI 服务，请检查网络与 Base URL",
            "timeout": "AI 服务响应超时",
            "auth": "AI 服务拒绝了凭据，请检查 API Key",
            "http": "AI 服务返回错误",
            "bad_response": "AI 返回内容无法识别，未判定为通过",
        }.get(self.kind, "AI 调用失败")
        return f"{prefix}：{self.detail}" if self.detail else prefix


@dataclass(frozen=True)
class Answer:
    passed: bool
    cycles: int
    hand: bool
    lean: bool
    confidence: float | None
    reason: str


def data_url(jpeg_bytes):
    return "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("ascii")


def endpoint(settings: AiSettings):
    base = settings.base_url
    if settings.protocol == "openai":
        return base if base.endswith("/chat/completions") else base + "/chat/completions"
    if settings.protocol == "anthropic":
        if base.endswith("/messages"):
            return base
        return base + "/messages" if base.endswith("/v1") else base + "/v1/messages"
    if ":generateContent" in base:
        return base.replace("{model}", quote(settings.model, safe=""))
    model = quote(settings.model, safe="")
    return (f"{base}/models/{model}:generateContent" if base.endswith(("/v1", "/v1beta"))
            else f"{base}/v1beta/models/{model}:generateContent")


def headers_for(settings: AiSettings):
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if settings.protocol == "anthropic":
        headers["anthropic-version"] = "2023-06-01"
        if settings.api_key:
            headers["x-api-key"] = settings.api_key
    elif settings.protocol == "gemini":
        if settings.api_key:
            headers["x-goog-api-key"] = settings.api_key
    elif settings.api_key:
        headers["Authorization"] = f"Bearer {settings.api_key}"
    return headers


def build_payload(settings: AiSettings, prompt, images):
    images = list(images or [])[:MAX_IMAGES]
    if settings.protocol == "openai":
        content = [{"type": "text", "text": prompt}]
        content += [{"type": "image_url", "image_url": {"url": data_url(item)}} for item in images]
        return {"model": settings.model, "temperature": 0, "max_tokens": 700, "stream": False,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                             {"role": "user", "content": content}]}
    if settings.protocol == "anthropic":
        content = [{"type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg",
                               "data": base64.b64encode(item).decode("ascii")}} for item in images]
        content.append({"type": "text", "text": prompt})
        return {"model": settings.model, "max_tokens": 700, "temperature": 0,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": content}]}
    parts = [{"inline_data": {"mime_type": "image/jpeg",
                              "data": base64.b64encode(item).decode("ascii")}} for item in images]
    parts.append({"text": prompt})
    return {"systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 700,
                                 "responseMimeType": "application/json"}}


def response_text(settings: AiSettings, data):
    """Join the assistant text out of a provider reply; unknown shapes fail closed."""
    try:
        if settings.protocol == "openai":
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, str):
                return content
            return "".join(part.get("text", "") for part in content if isinstance(part, dict))
        if settings.protocol == "anthropic":
            blocks = data["content"]
            return "".join(block.get("text", "") for block in blocks
                           if isinstance(block, dict) and block.get("type") == "text")
        candidates = data["candidates"]
        parts = candidates[0]["content"]["parts"]
        return "".join(part.get("text", "") for part in parts if isinstance(part, dict))
    except (KeyError, IndexError, TypeError) as error:
        raise VisionError("bad_response", "响应结构不匹配所选择的协议") from error


def extract_json_object(text):
    """Find the first balanced JSON object, tolerating fences and prose around it."""
    if not isinstance(text, str) or not text.strip():
        raise VisionError("bad_response", "模型没有返回内容")
    cleaned = text.strip()
    if "```" in cleaned:
        chunks = cleaned.split("```")
        for chunk in chunks[1:]:
            body = chunk[4:] if chunk.lower().startswith("json") else chunk
            cleaned = body.strip() or cleaned
            break
    start = cleaned.find("{")
    while start != -1:
        depth, in_string, escaped = 0, False, False
        for index in range(start, len(cleaned)):
            character = cleaned[index]
            if in_string:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    in_string = False
                continue
            if character == '"':
                in_string = True
            elif character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(cleaned[start:index + 1])
                    except ValueError:
                        break
                    if isinstance(parsed, dict):
                        return parsed
                    break
        start = cleaned.find("{", start + 1)
    raise VisionError("bad_response", "模型返回的不是 JSON 对象")


def _boolean(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false", "yes", "no"):
        return value.strip().lower() in ("true", "yes")
    return None


def _integer(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def parse_answer(text):
    """Strictly validate the model's verdict fields; contradictions never pass."""
    data = extract_json_object(text)

    def pick(*names):
        for name in names:
            if name in data:
                return data[name]
        return None

    passed = _boolean(pick("pass", "passed", "passes", "通过"))
    cycles = _integer(pick("motion_cycles", "cycles", "cycle_count", "动作次数"))
    hand = _boolean(pick("hand_on_belly", "hand", "hand_near_belly", "手放腹部"))
    lean = _boolean(pick("lean_observed", "lean", "leaning", "前倾"))
    reason = pick("reason", "说明", "note")
    confidence = pick("confidence")
    if passed is None:
        raise VisionError("bad_response", "缺少 pass 布尔字段")
    if cycles is None:
        raise VisionError("bad_response", "缺少 motion_cycles 整数字段")
    if hand is None:
        raise VisionError("bad_response", "缺少 hand_on_belly 布尔字段")
    if lean is None:
        raise VisionError("bad_response", "缺少 lean_observed 布尔字段")
    if not isinstance(reason, str):
        reason = ""
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        confidence = None
    return Answer(passed=passed, cycles=cycles, hand=hand, lean=lean,
                  confidence=None if confidence is None else float(confidence),
                  reason=reason.strip()[:200])


class VisionClient:
    def __init__(self, settings: AiSettings, timeout=REQUEST_TIMEOUT, opener=None):
        self.settings = settings
        self.timeout = timeout
        self.opener = opener or urllib.request.build_opener()

    def _post(self, prompt, images, limit=MAX_IMAGES):
        if not self.settings.configured:
            raise VisionError("config", "请先在设置中填写 Base URL 与模型 ID")
        url = endpoint(self.settings)
        payload = build_payload(self.settings, prompt, list(images)[:limit])
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(url, data=body, headers=headers_for(self.settings),
                                         method="POST")
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES)
        except urllib.error.HTTPError as error:
            try:
                detail = error.read(400).decode("utf-8", "replace").strip()
            except OSError:
                detail = ""
            kind = "auth" if error.code in (401, 403) else "http"
            raise VisionError(kind, f"HTTP {error.code} {detail}"[:300]) from error
        except (socket.timeout, TimeoutError) as error:
            raise VisionError("timeout", "超过 45 秒未返回") from error
        except urllib.error.URLError as error:
            reason = getattr(error, "reason", error)
            if isinstance(reason, (socket.timeout, TimeoutError, ssl.SSLError)):
                raise VisionError("timeout" if isinstance(reason, (socket.timeout, TimeoutError))
                                  else "network", str(reason)[:200]) from error
            raise VisionError("network", str(reason)[:200]) from error
        except OSError as error:
            raise VisionError("network", str(error)[:200]) from error
        try:
            data = json.loads(raw.decode("utf-8", "replace"))
        except ValueError as error:
            raise VisionError("bad_response", "响应不是 JSON") from error
        if not isinstance(data, dict):
            raise VisionError("bad_response", "响应不是对象")
        return data

    def evaluate(self, prompt, images):
        data = self._post(prompt, images)
        return parse_answer(response_text(self.settings, data))

    def ping(self):
        """Cheap reachability/credential probe; text only, no image is sent."""
        data = self._post("只回复 OK 两个字母。", [], limit=0)
        text = response_text(self.settings, data).strip()
        if not text:
            raise VisionError("bad_response", "模型未返回文本")
        return text[:120]
