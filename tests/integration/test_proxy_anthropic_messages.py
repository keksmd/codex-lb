from __future__ import annotations

import base64
import json

import pytest

import app.modules.proxy.service as proxy_module

pytestmark = pytest.mark.integration


def _encode_jwt(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    body = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    return f"header.{body}.sig"


def _make_auth_json(account_id: str, email: str) -> dict:
    payload = {
        "email": email,
        "chatgpt_account_id": account_id,
        "https://api.openai.com/auth": {"chatgpt_plan_type": "plus"},
    }
    return {
        "tokens": {
            "idToken": _encode_jwt(payload),
            "accessToken": "access-token",
            "refreshToken": "refresh-token",
            "accountId": account_id,
        },
    }


@pytest.mark.asyncio
async def test_v1_anthropic_messages_non_stream(async_client, monkeypatch):
    email = "anthropicnonstr@example.com"
    raw_account_id = "acc_anthropic_nonstr"
    auth_json = _make_auth_json(raw_account_id, email)
    files = {"auth_json": ("auth.json", json.dumps(auth_json), "application/json")}
    response = await async_client.post("/api/accounts/import", files=files)
    assert response.status_code == 200

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        yield 'data: {"type":"response.output_text.delta","delta":"hello"}\n\n'
        yield (
            'data: {"type":"response.completed","response":{"id":"resp_1","usage":'
            '{"input_tokens":3,"output_tokens":4,"total_tokens":7}}}\n\n'
        )

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.2", "messages": [{"role": "user", "content": "hi"}]}
    resp = await async_client.post(
        "/v1/messages",
        json=payload,
        headers={"anthropic-version": "2023-06-01"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "message"
    assert body["content"][0]["text"] == "hello"
    assert body["usage"]["input_tokens"] == 3
    assert body["usage"]["output_tokens"] == 4


@pytest.mark.asyncio
async def test_v1_anthropic_messages_stream(async_client, monkeypatch):
    email = "anthropicstream@example.com"
    raw_account_id = "acc_anthropic_stream"
    auth_json = _make_auth_json(raw_account_id, email)
    files = {"auth_json": ("auth.json", json.dumps(auth_json), "application/json")}
    response = await async_client.post("/api/accounts/import", files=files)
    assert response.status_code == 200

    async def fake_stream(payload, headers, access_token, account_id, base_url=None, raise_for_status=False):
        yield 'data: {"type":"response.output_text.delta","delta":"hi"}\n\n'
        yield (
            'data: {"type":"response.output_item.added","item":{"type":"function_call","call_id":"call_1",'
            '"name":"weather","arguments":"{\\"city\\":\\"Moscow\\"}"}}\n\n'
        )
        yield (
            'data: {"type":"response.completed","response":{"id":"resp_2","usage":'
            '{"input_tokens":2,"output_tokens":5,"total_tokens":7}}}\n\n'
        )

    monkeypatch.setattr(proxy_module, "core_stream_responses", fake_stream)

    payload = {"model": "gpt-5.2", "messages": [{"role": "user", "content": "hi"}], "stream": True}
    async with async_client.stream(
        "POST",
        "/v1/messages",
        json=payload,
        headers={"anthropic-version": "2023-06-01"},
    ) as resp:
        assert resp.status_code == 200
        body = await resp.aread()
    text = body.decode("utf-8")
    assert "event: message_start" in text
    assert '"type":"text_delta"' in text
    assert '"type":"tool_use"' in text
    assert '"type":"input_json_delta"' in text
    assert "event: message_stop" in text


@pytest.mark.asyncio
async def test_v1_anthropic_count_tokens(async_client):
    payload = {"model": "gpt-5.2", "messages": [{"role": "user", "content": "hi"}]}
    resp = await async_client.post(
        "/v1/messages/count_tokens",
        json=payload,
        headers={"anthropic-version": "2023-06-01"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["input_tokens"], int)
    assert body["input_tokens"] > 0
