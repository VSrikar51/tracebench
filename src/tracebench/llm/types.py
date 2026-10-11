"""The shapes of data our agent sends to and gets back from any LLM."""

from typing import Literal, Protocol

from pydantic import BaseModel


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class LLMResponse(BaseModel):
    message: Message
    model: str
    input_tokens: int
    output_tokens: int
    finish_reason: str


class LLMProvider(Protocol):
    name: str

    def chat(self, messages: list[Message]) -> LLMResponse: ...