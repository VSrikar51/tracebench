"""Adapter that lets our agent talk to a local model through Ollama."""

import uuid

from ollama import Client

from tracebench.llm.types import LLMResponse, Message, ToolCall, ToolSpec


def to_ollama_message(message: Message) -> dict:
    """Translate one of our messages into Ollama's format."""
    data = {"role": message.role, "content": message.content}
    if message.tool_calls:
        data["tool_calls"] = [
            {"function": {"name": call.name, "arguments": call.arguments}}
            for call in message.tool_calls
        ]
    if message.tool_name:
        data["tool_name"] = message.tool_name
    return data


def to_ollama_tool(spec: ToolSpec) -> dict:
    """Translate one of our menu items into Ollama's format."""
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
        },
    }


class OllamaProvider:
    name = "ollama"

    def __init__(self, model: str, think: bool = False, num_ctx: int = 8192) -> None:
        self.model = model
        self.think = think
        self.num_ctx = num_ctx
        self.client = Client()

    def chat(self, messages: list[Message], tools: list[ToolSpec] | None = None) -> LLMResponse:
        response = self.client.chat(
            model=self.model,
            messages=[to_ollama_message(message) for message in messages],
            tools=[to_ollama_tool(spec) for spec in tools] if tools else None,
            think=self.think,
            options={"num_ctx": self.num_ctx, "temperature": 0},
        )

        tool_calls = [
            ToolCall(
                id=f"call_{uuid.uuid4().hex[:8]}",
                name=call.function.name,
                arguments=dict(call.function.arguments or {}),
            )
            for call in response.message.tool_calls or []
        ]

        return LLMResponse(
            message=Message(
                role="assistant",
                content=response.message.content or "",
                tool_calls=tool_calls,
            ),
            model=self.model,
            input_tokens=response.prompt_eval_count or 0,
            output_tokens=response.eval_count or 0,
            finish_reason=response.done_reason or "unknown",
        )


if __name__ == "__main__":
    from tracebench.agent.registry import tool_specs
    from tracebench.config import settings

    provider = OllamaProvider(settings.agent_model, settings.agent_think, settings.agent_num_ctx)
    reply = provider.chat(
        [
            Message(role="system", content="You are a support agent for an online pet store."),
            Message(
                role="user",
                content="Hi, I'm chloe.garcia1@example.com. What's the status of my order 1001?",
            ),
        ],
        tools=tool_specs(),
    )

    print(f"Text: {reply.message.content!r}")
    for call in reply.message.tool_calls:
        print(f"Tool request: {call.name}({call.arguments})  [ticket {call.id}]")
    print(
        f"\n[{reply.input_tokens} tokens in, {reply.output_tokens} tokens out, "
        f"finish: {reply.finish_reason}]"
    )