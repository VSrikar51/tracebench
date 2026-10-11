"""The agent loop: ask the model, run the tools it wants, repeat until it answers."""

import json
from dataclasses import dataclass

from tracebench.agent.prompt import build_system_prompt
from tracebench.agent.registry import run_tool, tool_specs
from tracebench.config import settings
from tracebench.llm.types import LLMProvider, Message

MAX_STEPS = 8
FALLBACK_REPLY = "I'm sorry, I wasn't able to finish this request."


@dataclass
class AgentResult:
    reply: str
    messages: list[Message]
    steps: int
    stop_reason: str
    input_tokens: int
    output_tokens: int


def run_agent(provider: LLMProvider, user_message: str, max_steps: int = MAX_STEPS) -> AgentResult:
    """Run one customer message through the agent until it gives a final answer."""
    messages = [
        Message(role="system", content=build_system_prompt(settings.store_today)),
        Message(role="user", content=user_message),
    ]
    specs = tool_specs()
    input_tokens = 0
    output_tokens = 0

    for step in range(1, max_steps + 1):
        response = provider.chat(messages, tools=specs)
        input_tokens += response.input_tokens
        output_tokens += response.output_tokens
        messages.append(response.message)

        if not response.message.tool_calls:
            return AgentResult(
                reply=response.message.content,
                messages=messages,
                steps=step,
                stop_reason="answered",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        for call in response.message.tool_calls:
            result = run_tool(call.name, call.arguments)
            messages.append(Message(
                role="tool",
                content=json.dumps(result, ensure_ascii=False),
                tool_call_id=call.id,
                tool_name=call.name,
            ))

    return AgentResult(
        reply=FALLBACK_REPLY,
        messages=messages,
        steps=max_steps,
        stop_reason="step_limit",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def print_transcript(messages: list[Message]) -> None:
    """Show the conversation step by step, skipping the system prompt."""
    for message in messages:
        if message.role == "user":
            print(f"\n🧑 Customer: {message.content}")
        elif message.role == "assistant":
            if message.content:
                print(f"\n🤖 Agent: {message.content}")
            for call in message.tool_calls:
                print(f"   🛠️  {call.name}({json.dumps(call.arguments)})")
        elif message.role == "tool":
            preview = message.content[:200] + ("..." if len(message.content) > 200 else "")
            print(f"   📦 {message.tool_name} → {preview}")


if __name__ == "__main__":
    import sys
    import time

    from tracebench.llm.ollama_provider import OllamaProvider
    from tracebench.store.seed import seed

    seed()
    provider = OllamaProvider(settings.agent_model, settings.agent_think, settings.agent_num_ctx)

    started = time.perf_counter()
    result = run_agent(provider, " ".join(sys.argv[1:]))
    seconds = time.perf_counter() - started

    print_transcript(result.messages)
    print(
        f"\n[{result.stop_reason} after {result.steps} steps · "
        f"{result.input_tokens} tokens in, {result.output_tokens} tokens out · "
        f"{seconds:.1f}s]"
    )