from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.openai.chat_requests import ChatCompletionsRequest
from app.core.openai.chat_responses import ChatCompletion, _tool_call_delta_from_payload
from app.core.types import JsonValue
from app.core.utils.json_guards import is_json_list, is_json_mapping
from app.core.utils.sse import parse_sse_data_json


def _json_mapping(value: object) -> Mapping[str, JsonValue] | None:
    if not is_json_mapping(value):
        return None
    return cast(Mapping[str, JsonValue], value)


def _json_list(value: object) -> list[JsonValue] | None:
    if not is_json_list(value):
        return None
    return cast(list[JsonValue], value)


def _content_parts(content: JsonValue) -> list[JsonValue]:
    parts = _json_list(content)
    if parts is not None:
        return parts
    return [content]


def _first_text(blocks: list[Mapping[str, JsonValue]]) -> str:
    parts: list[str] = []
    for block in blocks:
        if block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
    return "\n\n".join(parts)


def _tool_result_text(content: JsonValue) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts = _json_list(content)
    if parts is not None:
        text_parts: list[str] = []
        for part in parts:
            part_map = _json_mapping(part)
            if part_map is not None and part_map.get("type") == "text":
                text = part_map.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
                continue
            if isinstance(part, str):
                text_parts.append(part)
        if text_parts:
            return "".join(text_parts)
    return json.dumps(content, ensure_ascii=False, separators=(",", ":"))


def _system_text(value: JsonValue | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    parts = _json_list(value)
    if parts is None:
        return None
    text_parts: list[str] = []
    for part in parts:
        part_map = _json_mapping(part)
        if part_map is None:
            continue
        if part_map.get("type") != "text":
            continue
        text = part_map.get("text")
        if isinstance(text, str) and text:
            text_parts.append(text)
    return "\n\n".join(text_parts) if text_parts else None


def _anthropic_image_to_chat_part(block: Mapping[str, JsonValue]) -> dict[str, JsonValue] | None:
    source = _json_mapping(block.get("source"))
    if source is None:
        return None
    source_type = source.get("type")
    if source_type == "base64":
        media_type = source.get("media_type")
        data = source.get("data")
        if isinstance(media_type, str) and isinstance(data, str):
            return {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{data}"}}
        return None
    if source_type == "url":
        url = source.get("url")
        if isinstance(url, str) and url:
            return {"type": "image_url", "image_url": {"url": url}}
    return None


def _user_blocks_to_chat_messages(blocks: list[Mapping[str, JsonValue]]) -> list[dict[str, JsonValue]]:
    messages: list[dict[str, JsonValue]] = []
    pending_parts: list[JsonValue] = []
    for block in blocks:
        block_type = block.get("type")
        if block_type == "tool_result":
            if pending_parts:
                messages.append({"role": "user", "content": pending_parts})
                pending_parts = []
            tool_use_id = block.get("tool_use_id")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_use_id if isinstance(tool_use_id, str) else f"toolu_{uuid4().hex}",
                    "content": _tool_result_text(block.get("content")),
                }
            )
            continue
        if block_type == "text":
            text = block.get("text")
            if isinstance(text, str):
                pending_parts.append({"type": "text", "text": text})
            continue
        if block_type == "image":
            image_part = _anthropic_image_to_chat_part(block)
            if image_part is not None:
                pending_parts.append(image_part)
            continue
    if pending_parts:
        content: JsonValue = pending_parts
        if len(pending_parts) == 1 and is_json_mapping(pending_parts[0]) and pending_parts[0].get("type") == "text":
            content = cast(Mapping[str, JsonValue], pending_parts[0]).get("text") or ""
        messages.append({"role": "user", "content": content})
    return messages


def _assistant_blocks_to_chat_message(blocks: list[Mapping[str, JsonValue]]) -> dict[str, JsonValue]:
    content = _first_text(blocks)
    tool_calls: list[JsonValue] = []
    for block in blocks:
        if block.get("type") != "tool_use":
            continue
        tool_name = block.get("name")
        if not isinstance(tool_name, str) or not tool_name:
            continue
        tool_id = block.get("id")
        tool_input = block.get("input")
        tool_calls.append(
            {
                "id": tool_id if isinstance(tool_id, str) else f"toolu_{uuid4().hex}",
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps(tool_input if tool_input is not None else {}, ensure_ascii=False),
                },
            }
        )
    message: dict[str, JsonValue] = {"role": "assistant", "content": content or ""}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return message


def _anthropic_messages_to_chat_messages(messages: list[dict[str, JsonValue]]) -> list[dict[str, JsonValue]]:
    chat_messages: list[dict[str, JsonValue]] = []
    for message in messages:
        role = message.get("role")
        if role not in {"user", "assistant"}:
            continue
        content = message.get("content")
        if isinstance(content, str):
            chat_messages.append({"role": role, "content": content})
            continue
        parts = _json_list(content)
        if parts is None:
            chat_messages.append({"role": role, "content": ""})
            continue
        mapped_parts = [part for part in (_json_mapping(part) for part in parts) if part is not None]
        if role == "assistant":
            chat_messages.append(_assistant_blocks_to_chat_message(mapped_parts))
            continue
        chat_messages.extend(_user_blocks_to_chat_messages(mapped_parts))
    return chat_messages


def _map_tools(tools: list[JsonValue]) -> list[JsonValue]:
    mapped: list[JsonValue] = []
    for tool in tools:
        tool_map = _json_mapping(tool)
        if tool_map is None:
            continue
        name = tool_map.get("name")
        if not isinstance(name, str) or not name:
            continue
        mapped.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool_map.get("description"),
                    "parameters": tool_map.get("input_schema") if tool_map.get("input_schema") is not None else {},
                },
            }
        )
    return mapped


def _map_tool_choice(tool_choice: JsonValue | None) -> JsonValue | None:
    choice_map = _json_mapping(tool_choice)
    if choice_map is None:
        return None
    choice_type = choice_map.get("type")
    if choice_type == "auto":
        return "auto"
    if choice_type == "any":
        return "required"
    if choice_type == "none":
        return "none"
    if choice_type == "tool":
        name = choice_map.get("name")
        if isinstance(name, str) and name:
            return {"type": "function", "function": {"name": name}}
    return None


def _map_output_config(output_config: JsonValue | None) -> JsonValue | None:
    output_map = _json_mapping(output_config)
    if output_map is None:
        return None
    format_map = _json_mapping(output_map.get("format"))
    if format_map is None:
        return None
    format_type = format_map.get("type")
    if format_type == "json_object":
        return {"type": "json_object"}
    if format_type == "json_schema":
        result: dict[str, JsonValue] = {"type": "json_schema", "json_schema": {}}
        json_schema = cast(dict[str, JsonValue], result["json_schema"])
        name = format_map.get("name")
        if isinstance(name, str) and name:
            json_schema["name"] = name
        schema = format_map.get("schema")
        if schema is not None:
            json_schema["schema"] = schema
        strict = format_map.get("strict")
        if isinstance(strict, bool):
            json_schema["strict"] = strict
        return result
    return None


class AnthropicMessagesRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str = Field(min_length=1)
    messages: list[dict[str, JsonValue]]
    system: JsonValue | None = None
    tools: list[JsonValue] = Field(default_factory=list)
    tool_choice: JsonValue | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    stop_sequences: list[str] | None = None
    stream: bool | None = None
    output_config: JsonValue | None = None
    service_tier: str | None = None

    @model_validator(mode="after")
    def _validate_messages(self) -> "AnthropicMessagesRequest":
        if not self.messages:
            raise ValueError("'messages' must be a non-empty list.")
        for message in self.messages:
            role = message.get("role")
            if role not in {"user", "assistant"}:
                raise ValueError("Each message must include role 'user' or 'assistant'.")
        return self

    def to_chat_completions_request(self) -> ChatCompletionsRequest:
        messages = _anthropic_messages_to_chat_messages(self.messages)
        system_text = _system_text(self.system)
        if system_text:
            messages.insert(0, {"role": "system", "content": system_text})
        payload: dict[str, JsonValue] = {
            "model": self.model,
            "messages": messages,
        }
        tools = _map_tools(self.tools)
        if tools:
            payload["tools"] = tools
        tool_choice = _map_tool_choice(self.tool_choice)
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.stop_sequences:
            payload["stop"] = self.stop_sequences
        if self.stream is not None:
            payload["stream"] = self.stream
        if self.service_tier is not None:
            payload["service_tier"] = self.service_tier
        response_format = _map_output_config(self.output_config)
        if response_format is not None:
            payload["response_format"] = response_format
        return ChatCompletionsRequest.model_validate(payload)


class AnthropicCountTokensResponse(BaseModel):
    input_tokens: int


class AnthropicUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


def _usage_from_chat_completion(completion: ChatCompletion) -> AnthropicUsage:
    usage = completion.usage
    if usage is None:
        return AnthropicUsage()
    return AnthropicUsage(
        input_tokens=usage.prompt_tokens or 0,
        output_tokens=usage.completion_tokens or 0,
    )


def _map_stop_reason(finish_reason: str | None) -> str:
    if finish_reason == "tool_calls":
        return "tool_use"
    if finish_reason == "length":
        return "max_tokens"
    if finish_reason == "content_filter":
        return "refusal"
    return "end_turn"


def anthropic_message_from_chat_completion(completion: ChatCompletion) -> dict[str, JsonValue]:
    choice = completion.choices[0]
    content: list[JsonValue] = []
    message = choice.message
    if isinstance(message.content, str) and message.content:
        content.append({"type": "text", "text": message.content})
    for tool_call in message.tool_calls or []:
        function = tool_call.function
        tool_input: JsonValue = {}
        arguments = function.arguments if function is not None else None
        if isinstance(arguments, str) and arguments:
            try:
                tool_input = json.loads(arguments)
            except json.JSONDecodeError:
                tool_input = {"raw": arguments}
        content.append(
            {
                "type": "tool_use",
                "id": tool_call.id or f"toolu_{uuid4().hex}",
                "name": function.name if function is not None and function.name else "tool",
                "input": tool_input,
            }
        )
    return {
        "id": completion.id.replace("chatcmpl_", "msg_") if completion.id else f"msg_{uuid4().hex}",
        "type": "message",
        "role": "assistant",
        "content": content,
        "model": completion.model,
        "stop_reason": _map_stop_reason(choice.finish_reason),
        "stop_sequence": None,
        "usage": _usage_from_chat_completion(completion).model_dump(mode="json"),
    }


def approximate_anthropic_input_tokens(request: AnthropicMessagesRequest) -> int:
    chat_request = request.to_chat_completions_request()
    raw = chat_request.model_dump_json(exclude_none=True)
    return max(1, round(len(raw) / 4))


def _dump_event(event: str, payload: Mapping[str, JsonValue]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"


def _error_event(message: str, error_type: str = "api_error") -> str:
    return _dump_event(
        "error",
        {
            "type": "error",
            "error": {
                "type": error_type,
                "message": message,
            },
        },
    )


@dataclass(slots=True)
class _ToolBlockState:
    stream_index: int
    content_index: int
    call_id: str
    name: str
    started: bool = False


@dataclass(slots=True)
class _AnthropicStreamState:
    model: str
    response_id: str = field(default_factory=lambda: f"msg_{uuid4().hex}")
    created: int = field(default_factory=lambda: int(time.time()))
    text_block_started: bool = False
    text_block_closed: bool = False
    next_content_index: int = 0
    saw_tool_use: bool = False
    tool_blocks: dict[int, _ToolBlockState] = field(default_factory=dict)
    tool_indexer: "_ToolCallIndexer" = field(default_factory=lambda: _ToolCallIndexer())


def _response_usage(payload: Mapping[str, JsonValue]) -> AnthropicUsage:
    response = _json_mapping(payload.get("response"))
    if response is None:
        return AnthropicUsage()
    usage = _json_mapping(response.get("usage"))
    if usage is None:
        return AnthropicUsage()
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    return AnthropicUsage(
        input_tokens=input_tokens if isinstance(input_tokens, int) else 0,
        output_tokens=output_tokens if isinstance(output_tokens, int) else 0,
    )


def _ensure_tool_block(
    state: _AnthropicStreamState,
    stream_index: int,
    tool_delta: object,
) -> _ToolBlockState:
    block = state.tool_blocks.get(stream_index)
    if block is not None:
        return block
    tool_call = cast(object, tool_delta)
    call_id = getattr(tool_call, "call_id", None) or f"toolu_{uuid4().hex}"
    name = getattr(tool_call, "name", None) or "tool"
    block = _ToolBlockState(
        stream_index=stream_index,
        content_index=state.next_content_index,
        call_id=call_id,
        name=name,
    )
    state.next_content_index += 1
    state.tool_blocks[stream_index] = block
    return block


async def stream_anthropic_messages(stream: AsyncIterator[str], model: str) -> AsyncIterator[str]:
    state = _AnthropicStreamState(model=model)
    started = False
    async for line in stream:
        payload = parse_sse_data_json(line)
        if not payload:
            continue
        if not started:
            started = True
            yield _dump_event(
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": state.response_id,
                        "type": "message",
                        "role": "assistant",
                        "content": [],
                        "model": state.model,
                        "stop_reason": None,
                        "stop_sequence": None,
                        "usage": AnthropicUsage().model_dump(mode="json"),
                    },
                },
            )
        response = _json_mapping(payload.get("response"))
        if response is not None:
            response_id = response.get("id")
            if isinstance(response_id, str) and response_id:
                state.response_id = response_id.replace("resp_", "msg_")
        event_type = payload.get("type")
        if event_type == "response.output_text.delta":
            if not state.text_block_started:
                state.text_block_started = True
                yield _dump_event(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": 0,
                        "content_block": {"type": "text", "text": ""},
                    },
                )
                state.next_content_index = max(state.next_content_index, 1)
            delta = payload.get("delta")
            yield _dump_event(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {
                        "type": "text_delta",
                        "text": delta if isinstance(delta, str) else "",
                    },
                },
            )
            continue
        tool_delta = _tool_call_delta_from_payload(payload, state.tool_indexer)
        if tool_delta is not None:
            state.saw_tool_use = True
            block = _ensure_tool_block(state, tool_delta.index, tool_delta)
            delta_call_id = getattr(tool_delta, "call_id", None)
            if isinstance(delta_call_id, str) and delta_call_id:
                block.call_id = delta_call_id
            delta_name = getattr(tool_delta, "name", None)
            if isinstance(delta_name, str) and delta_name:
                block.name = delta_name
            if not block.started:
                block.started = True
                yield _dump_event(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": block.content_index,
                        "content_block": {
                            "type": "tool_use",
                            "id": block.call_id,
                            "name": block.name,
                            "input": {},
                        },
                    },
                )
            arguments = getattr(tool_delta, "arguments", None)
            if isinstance(arguments, str) and arguments:
                yield _dump_event(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": block.content_index,
                        "delta": {
                            "type": "input_json_delta",
                            "partial_json": arguments,
                        },
                    },
                )
            continue
        if event_type in ("response.failed", "error"):
            error_map = _json_mapping(payload.get("error"))
            if event_type == "response.failed":
                response_map = _json_mapping(payload.get("response"))
                if response_map is not None:
                    nested = _json_mapping(response_map.get("error"))
                    if nested is not None:
                        error_map = nested
            message = "Upstream request failed"
            error_type = "api_error"
            if error_map is not None:
                maybe_message = error_map.get("message")
                maybe_type = error_map.get("type")
                if isinstance(maybe_message, str) and maybe_message:
                    message = maybe_message
                if isinstance(maybe_type, str) and maybe_type:
                    error_type = maybe_type
            yield _error_event(message, error_type)
            return
        if event_type in ("response.completed", "response.incomplete"):
            if state.text_block_started and not state.text_block_closed:
                state.text_block_closed = True
                yield _dump_event(
                    "content_block_stop",
                    {"type": "content_block_stop", "index": 0},
                )
            for block in sorted(state.tool_blocks.values(), key=lambda item: item.content_index):
                if block.started:
                    yield _dump_event(
                        "content_block_stop",
                        {"type": "content_block_stop", "index": block.content_index},
                    )
            usage = _response_usage(payload)
            stop_reason = "tool_use" if state.saw_tool_use else "end_turn"
            yield _dump_event(
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {
                        "stop_reason": stop_reason,
                        "stop_sequence": None,
                    },
                    "usage": usage.model_dump(mode="json"),
                },
            )
            yield _dump_event("message_stop", {"type": "message_stop"})
            return


class _ToolCallIndexer:
    def __init__(self) -> None:
        self._indexes: dict[str, int] = {}
        self._next = 0

    def index_for(self, call_id: str | None, name: str | None) -> int:
        if call_id:
            key = f"id:{call_id}"
        elif name:
            key = f"name:{name}"
        else:
            key = f"anon:{self._next}"
        if key not in self._indexes:
            self._indexes[key] = self._next
            self._next += 1
        return self._indexes[key]
