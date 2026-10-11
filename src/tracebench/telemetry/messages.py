"""Convert our messages into the OpenTelemetry GenAI message format for traces."""

from tracebench.llm.types import LLMResponse, Message


def to_otel_parts(message: Message) -> list[dict]:
    """Split one message into the spec's "parts": text, tool requests, or a tool result."""
    if message.role == "tool":
        return [{
            "type": "tool_call_response",
            "id": message.tool_call_id,
            "response": message.content,
        }]

    parts = []
    if message.content:
        parts.append({"type": "text", "content": message.content})
    for call in message.tool_calls:
        parts.append({
            "type": "tool_call",
            "id": call.id,
            "name": call.name,
            "arguments": call.arguments,
        })
    return parts


def to_otel_messages(messages: list[Message]) -> list[dict]:
    """The full conversation sent to the model, in the spec's format."""
    return [{"role": message.role, "parts": to_otel_parts(message)} for message in messages]


def to_otel_output(response: LLMResponse) -> list[dict]:
    """The model's reply, in the spec's format."""
    return [{
        "role": "assistant",
        "parts": to_otel_parts(response.message),
        "finish_reason": response.finish_reason,
    }]