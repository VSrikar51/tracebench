"""Adapter that lets our agent talk to a local model through Ollama."""

from ollama import Client

from tracebench.llm.types import LLMResponse, Message


class OllamaProvider:
    name = "ollama"

    def __init__(self, model: str, think: bool = False, num_ctx: int = 8192) -> None:
        self.model = model
        self.think = think
        self.num_ctx = num_ctx
        self.client = Client()

    def chat(self, messages: list[Message]) -> LLMResponse:
        response = self.client.chat(
            model=self.model,
            messages=[message.model_dump() for message in messages],
            think=self.think,
            options={"num_ctx": self.num_ctx, "temperature": 0},
        )
        return LLMResponse(
            message=Message(role="assistant", content=response.message.content or ""),
            model=self.model,
            input_tokens=response.prompt_eval_count or 0,
            output_tokens=response.eval_count or 0,
            finish_reason=response.done_reason or "unknown",
        )


if __name__ == "__main__":
    from tracebench.config import settings

    provider = OllamaProvider(settings.agent_model, settings.agent_think, settings.agent_num_ctx)
    reply = provider.chat([
        Message(role="system", content="You are a friendly support agent for an online pet store."),
        Message(role="user", content="Hi! What kinds of things can you help me with?"),
    ])
    print(reply.message.content)
    print(
        f"\n[{reply.input_tokens} tokens in, {reply.output_tokens} tokens out, "
        f"finish: {reply.finish_reason}]"
    )