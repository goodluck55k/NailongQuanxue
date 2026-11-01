import io
import json
import socket
import urllib.error

import pytest

from app.ai_config import AiSettings
from app.vision_api import (MAX_IMAGES, VisionClient, VisionError, build_payload, endpoint,
                            extract_json_object, headers_for, parse_answer, response_text)


class Reply:
    def __init__(self, body):
        self.body = body

    def read(self, size=-1):
        return self.body if size is None or size < 0 else self.body[:size]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class Opener:
    """Stands in for urllib's opener so no network call is made."""

    def __init__(self, result):
        self.result = result
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append((request, timeout))
        if isinstance(self.result, BaseException):
            raise self.result
        return Reply(self.result)


def settings(protocol="openai", **extra):
    values = {"protocol": protocol, "base_url": "https://api.example.com/v1",
              "api_key": "sk-test", "model": "vision-1"}
    values.update(extra)
    return AiSettings(**values)


def openai_reply(payload):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return json.dumps({"choices": [{"message": {"content": text}}]}).encode()


def answer_text(**overrides):
    data = {"pass": True, "motion_cycles": 2, "hand_on_belly": True, "lean_observed": True,
            "confidence": 0.8, "reason": "两组前倾回正"}
    data.update(overrides)
    return json.dumps(data)


def test_endpoint_per_protocol():
    assert endpoint(settings()) == "https://api.example.com/v1/chat/completions"
    assert endpoint(settings(base_url="https://api.example.com/v1/chat/completions")) == \
        "https://api.example.com/v1/chat/completions"
    assert endpoint(settings("anthropic")) == "https://api.example.com/v1/messages"
    assert endpoint(settings("anthropic", base_url="https://api.example.com")) == \
        "https://api.example.com/v1/messages"
    assert endpoint(settings("anthropic", base_url="https://api.example.com/v1/messages")) == \
        "https://api.example.com/v1/messages"
    assert endpoint(settings("gemini")) == \
        "https://api.example.com/v1/models/vision-1:generateContent"
    assert endpoint(settings("gemini", base_url="https://generativelanguage.test")) == \
        "https://generativelanguage.test/v1beta/models/vision-1:generateContent"
    assert endpoint(settings("gemini", base_url="https://generativelanguage.test/v1beta")) == \
        "https://generativelanguage.test/v1beta/models/vision-1:generateContent"


def test_headers_per_protocol():
    bearer = headers_for(settings())
    assert bearer["Authorization"] == "Bearer sk-test"
    anthropic = headers_for(settings("anthropic"))
    assert anthropic["x-api-key"] == "sk-test"
    assert anthropic["anthropic-version"] == "2023-06-01"
    assert "Authorization" not in anthropic
    gemini = headers_for(settings("gemini"))
    assert gemini["x-goog-api-key"] == "sk-test"


def test_payload_shapes_and_image_cap():
    images = [b"\xff\xd8" + bytes([index]) for index in range(MAX_IMAGES + 4)]
    openai = build_payload(settings(), "check", images)
    content = openai["messages"][1]["content"]
    assert content[0]["type"] == "text"
    assert sum(1 for part in content if part["type"] == "image_url") == MAX_IMAGES
    anthropic = build_payload(settings("anthropic"), "check", images)
    blocks = anthropic["messages"][0]["content"]
    assert blocks[-1]["type"] == "text"
    assert sum(1 for block in blocks if block["type"] == "image") == MAX_IMAGES
    gemini = build_payload(settings("gemini"), "check", images)
    parts = gemini["contents"][0]["parts"]
    assert parts[-1]["text"] == "check"
    assert gemini["generationConfig"]["responseMimeType"] == "application/json"


def test_response_text_per_protocol():
    assert response_text(settings(), {"choices": [{"message": {"content": "ok"}}]}) == "ok"
    assert response_text(settings("anthropic"),
                         {"content": [{"type": "text", "text": "a"},
                                      {"type": "tool_use", "text": "skip"},
                                      {"type": "text", "text": "b"}]}) == "ab"
    assert response_text(settings("gemini"),
                         {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}) == "ok"
    with pytest.raises(VisionError) as error:
        response_text(settings(), {"unexpected": True})
    assert error.value.kind == "bad_response"


def test_extract_json_object_handles_fences_and_prose():
    fenced = '结果如下：\n```json\n{"pass": true}\n```\n结束'
    assert extract_json_object(fenced) == {"pass": True}
    assert extract_json_object('前缀 {"a": {"b": 1}} 后缀') == {"a": {"b": 1}}
    with pytest.raises(VisionError):
        extract_json_object("")
    with pytest.raises(VisionError):
        extract_json_object("没有对象")


def test_parse_answer_accepts_aliases_and_rejects_missing_fields():
    answer = parse_answer(answer_text())
    assert answer.passed and answer.cycles == 2 and answer.hand and answer.lean
    alias = parse_answer(json.dumps({"passed": "true", "cycles": "3", "hand": "yes",
                                     "lean": "true", "note": "说明"}))
    assert alias.passed and alias.cycles == 3 and alias.reason == "说明"
    for missing in ("pass", "motion_cycles", "hand_on_belly", "lean_observed"):
        broken = {"pass": True, "motion_cycles": 2, "hand_on_belly": True, "lean_observed": True}
        broken.pop(missing)
        with pytest.raises(VisionError) as error:
            parse_answer(json.dumps(broken))
        assert error.value.kind == "bad_response"
    with pytest.raises(VisionError):
        parse_answer(json.dumps({"pass": "maybe", "motion_cycles": 2, "hand_on_belly": True,
                                 "lean_observed": True}))


def test_evaluate_success_and_failures_are_typed():
    opener = Opener(openai_reply(answer_text()))
    answer = VisionClient(settings(), opener=opener).evaluate("prompt", [b"\xff\xd8x"])
    assert answer.passed and answer.cycles == 2
    request, timeout = opener.requests[0]
    assert request.full_url == "https://api.example.com/v1/chat/completions"
    assert request.get_method() == "POST"
    assert timeout == 45

    auth = urllib.error.HTTPError("https://api.example.com", 401, "Unauthorized", None,
                                  io.BytesIO(b"nope"))
    with pytest.raises(VisionError) as error:
        VisionClient(settings(), opener=Opener(auth)).evaluate("p", [])
    assert error.value.kind == "auth"

    server = urllib.error.HTTPError("https://api.example.com", 500, "Server", None,
                                    io.BytesIO(b"boom"))
    with pytest.raises(VisionError) as error:
        VisionClient(settings(), opener=Opener(server)).evaluate("p", [])
    assert error.value.kind == "http" and "500" in error.value.detail

    with pytest.raises(VisionError) as error:
        VisionClient(settings(), opener=Opener(socket.timeout("slow"))).evaluate("p", [])
    assert error.value.kind == "timeout"

    with pytest.raises(VisionError) as error:
        VisionClient(settings(), opener=Opener(urllib.error.URLError("offline"))).evaluate("p", [])
    assert error.value.kind == "network"

    with pytest.raises(VisionError) as error:
        VisionClient(settings(), opener=Opener(b"<html>")).evaluate("p", [])
    assert error.value.kind == "bad_response"


def test_unconfigured_settings_never_call_the_network():
    opener = Opener(openai_reply(answer_text()))
    with pytest.raises(VisionError) as error:
        VisionClient(AiSettings(), opener=opener).evaluate("p", [])
    assert error.value.kind == "config"
    assert opener.requests == []


def test_ping_returns_short_text():
    opener = Opener(openai_reply("OK"))
    assert VisionClient(settings(), opener=opener).ping() == "OK"
    with pytest.raises(VisionError):
        VisionClient(settings(), opener=Opener(openai_reply("   "))).ping()


def test_error_messages_are_user_facing_chinese():
    for kind in ("config", "network", "timeout", "auth", "http", "bad_response"):
        message = VisionError(kind, "细节").user_message()
        assert "细节" in message
        assert any(ord(character) > 127 for character in message)
