"""The shapes of data our agent sends to and gets back from any LLM."""

from typing import Literal, Protocol

from pydantic import BaseModel


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = []
    tool_call_id: str | None = None
    tool_name: str | None = None


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict


class LLMResponse(BaseModel):
    message: Message
    model: str
    input_tokens: int
    output_tokens: int
    finish_reason: str


class LLMProvider(Protocol):
    name: str
    model: str

    def chat(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        response_format: dict | None = None,
    ) -> LLMResponse: ...