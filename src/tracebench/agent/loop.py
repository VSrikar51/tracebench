"""The agent loop: ask the model, run the tools it wants, repeat until it answers.

Every run is traced: one invoke_agent span, with a chat span for each model
call and an execute_tool span for each tool call inside it.
"""

import json
from dataclasses import dataclass

from opentelemetry.trace import SpanKind, Status, StatusCode

from tracebench.agent.prompt import build_system_prompt
from tracebench.agent.registry import run_tool, tool_specs
from tracebench.config import settings
from tracebench.llm.types import LLMProvider, LLMResponse, Message, ToolCall, ToolSpec
from tracebench.telemetry import attributes as attr
from tracebench.telemetry.messages import to_otel_messages, to_otel_output
from tracebench.telemetry.setup import get_tracer
from tracebench.telemetry.cost import BudgetExceeded, BudgetGuard, cost_usd, get_budget_guard, price_for

AGENT_NAME = "support_agent"
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
    cost_usd: float
    trace_id: str


def call_model(
    provider: LLMProvider, messages: list[Message], specs: list[ToolSpec], guard: BudgetGuard
) -> tuple[LLMResponse, float]:
    """One model call, wrapped in a chat span. Returns the response and its cost."""
    guard.check()

    with get_tracer().start_as_current_span(f"chat {provider.model}", kind=SpanKind.CLIENT) as span:
        span.set_attribute(attr.OPERATION_NAME, "chat")
        span.set_attribute(attr.PROVIDER_NAME, provider.name)
        span.set_attribute(attr.REQUEST_MODEL, provider.model)
        if settings.trace_content:
            span.set_attribute(
                attr.INPUT_MESSAGES, json.dumps(to_otel_messages(messages), ensure_ascii=False)
            )

        response = provider.chat(messages, tools=specs)
        cost = cost_usd(provider.model, response.input_tokens, response.output_tokens)
        guard.add(cost)

        span.set_attribute(attr.RESPONSE_MODEL, response.model)
        span.set_attribute(attr.USAGE_INPUT_TOKENS, response.input_tokens)
        span.set_attribute(attr.USAGE_OUTPUT_TOKENS, response.output_tokens)
        span.set_attribute(attr.RESPONSE_FINISH_REASONS, [response.finish_reason])
        span.set_attribute(attr.COST_USD, cost)
        if settings.trace_content:
            span.set_attribute(
                attr.OUTPUT_MESSAGES, json.dumps(to_otel_output(response), ensure_ascii=False)
            )
        return response, cost


def call_tool(call: ToolCall) -> dict:
    """One tool run, wrapped in an execute_tool span."""
    with get_tracer().start_as_current_span(f"execute_tool {call.name}") as span:
        span.set_attribute(attr.OPERATION_NAME, "execute_tool")
        span.set_attribute(attr.TOOL_NAME, call.name)
        span.set_attribute(attr.TOOL_CALL_ID, call.id)
        if settings.trace_content:
            span.set_attribute(
                attr.TOOL_CALL_ARGUMENTS, json.dumps(call.arguments, ensure_ascii=False)
            )

        result = run_tool(call.name, call.arguments)

        if settings.trace_content:
            span.set_attribute(attr.TOOL_CALL_RESULT, json.dumps(result, ensure_ascii=False))
        if "error" in result:
            span.set_attribute(attr.ERROR_TYPE, "tool_error")
            span.set_status(Status(StatusCode.ERROR, result["error"]))
        return result


def run_agent(provider: LLMProvider, user_message: str, max_steps: int = MAX_STEPS) -> AgentResult:
    """Run one customer message through the agent until it gives a final answer."""
    price_for(provider.model)
    guard = get_budget_guard(provider.name)

    with get_tracer().start_as_current_span(f"invoke_agent {AGENT_NAME}") as agent_span:
        agent_span.set_attribute(attr.OPERATION_NAME, "invoke_agent")
        agent_span.set_attribute(attr.AGENT_NAME, AGENT_NAME)
        agent_span.set_attribute(attr.PROVIDER_NAME, provider.name)
        agent_span.set_attribute(attr.REQUEST_MODEL, provider.model)
        trace_id = format(agent_span.get_span_context().trace_id, "032x")

        messages = [
            Message(role="system", content=build_system_prompt(settings.store_today)),
            Message(role="user", content=user_message),
        ]
        specs = tool_specs()
        input_tokens = 0
        output_tokens = 0
        total_cost = 0.0
        reply = FALLBACK_REPLY
        stop_reason = "step_limit"
        steps = max_steps

        for step in range(1, max_steps + 1):
            try:
                response, cost = call_model(provider, messages, specs, guard)
            except BudgetExceeded as error:
                stop_reason = "budget_exceeded"
                steps = step
                agent_span.set_status(Status(StatusCode.ERROR, str(error)))
                break
            except Exception as error:
                stop_reason = "model_error"
                steps = step
                agent_span.set_status(Status(StatusCode.ERROR, f"Model call failed: {error}"))
                break

            input_tokens += response.input_tokens
            output_tokens += response.output_tokens
            total_cost += cost
            messages.append(response.message)

            if not response.message.tool_calls:
                reply = response.message.content
                stop_reason = "answered"
                steps = step
                break

            for call in response.message.tool_calls:
                result = call_tool(call)
                messages.append(Message(
                    role="tool",
                    content=json.dumps(result, ensure_ascii=False),
                    tool_call_id=call.id,
                    tool_name=call.name,
                ))

        if stop_reason == "step_limit":
            agent_span.set_status(Status(StatusCode.ERROR, f"No answer after {max_steps} steps"))

        agent_span.set_attribute(attr.AGENT_STEPS, steps)
        agent_span.set_attribute(attr.AGENT_STOP_REASON, stop_reason)
        agent_span.set_attribute(attr.USAGE_INPUT_TOKENS, input_tokens)
        agent_span.set_attribute(attr.USAGE_OUTPUT_TOKENS, output_tokens)
        agent_span.set_attribute(attr.COST_USD, total_cost)

    return AgentResult(
        reply=reply,
        messages=messages,
        steps=steps,
        stop_reason=stop_reason,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=total_cost,
        trace_id=trace_id,
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
    from tracebench.telemetry.setup import setup_tracing
    

    tracing = setup_tracing()
    seed()
    provider = OllamaProvider(settings.agent_model, settings.agent_think, settings.agent_num_ctx)

    started = time.perf_counter()
    result = run_agent(provider, " ".join(sys.argv[1:]))
    seconds = time.perf_counter() - started

    print_transcript(result.messages)
    print(
        f"\n[{result.stop_reason} after {result.steps} steps · "
        f"{result.input_tokens} tokens in, {result.output_tokens} tokens out · "
        f"${result.cost_usd:.6f} · {seconds:.1f}s]"
    )

    tracing.force_flush()
    print(f"\n🧾 Trace ID: {result.trace_id}")