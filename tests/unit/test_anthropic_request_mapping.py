from __future__ import annotations

from app.core.anthropic import AnthropicMessagesRequest, anthropic_message_from_chat_completion
from app.core.openai.chat_responses import (
    ChatCompletion,
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionUsage,
    ChatMessageToolCall,
    ChatToolCallFunction,
)


def test_anthropic_messages_to_chat_mapping():
    payload = {
        "model": "gpt-5.2",
        "system": "sys",
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "weather?"}]},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Checking"},
                    {"type": "tool_use", "id": "toolu_1", "name": "weather", "input": {"city": "Moscow"}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_1", "content": [{"type": "text", "text": "Sunny"}]}
                ],
            },
        ],
        "tools": [{"name": "weather", "description": "desc", "input_schema": {"type": "object"}}],
        "tool_choice": {"type": "tool", "name": "weather"},
        "output_config": {"format": {"type": "json_object"}},
    }
    req = AnthropicMessagesRequest.model_validate(payload)
    chat = req.to_chat_completions_request()
    assert chat.messages[0] == {"role": "system", "content": "sys"}
    assert chat.messages[1]["role"] == "user"
    assert chat.messages[2]["role"] == "assistant"
    assert chat.messages[2]["tool_calls"][0]["function"]["name"] == "weather"
    assert chat.messages[3]["role"] == "tool"
    assert chat.messages[3]["tool_call_id"] == "toolu_1"
    assert chat.tool_choice == {"type": "function", "function": {"name": "weather"}}
    assert chat.response_format == {"type": "json_object"}


def test_anthropic_response_maps_from_chat_completion():
    completion = ChatCompletion(
        id="chatcmpl_123",
        created=1,
        model="gpt-5.2",
        choices=[
            ChatCompletionChoice(
                index=0,
                finish_reason="tool_calls",
                message=ChatCompletionMessage(
                    role="assistant",
                    content="Checking",
                    tool_calls=[
                        ChatMessageToolCall(
                            id="call_1",
                            function=ChatToolCallFunction(name="weather", arguments='{"city":"Moscow"}'),
                        )
                    ],
                ),
            )
        ],
        usage=ChatCompletionUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )
    mapped = anthropic_message_from_chat_completion(completion)
    assert mapped["id"] == "msg_123"
    assert mapped["stop_reason"] == "tool_use"
    assert mapped["usage"]["input_tokens"] == 10
    assert mapped["usage"]["output_tokens"] == 5
    assert mapped["content"][0]["type"] == "text"
    assert mapped["content"][1]["type"] == "tool_use"
