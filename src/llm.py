"""LLM adapters: Anthropic (Claude) and OpenAI-compatible (GLM 5.2 via Z.ai / OpenRouter).

Each adapter exposes:
    generate(system, user, max_tokens) -> str
Anthropic additionally exposes:
    research(prompt, max_tokens) -> str   # uses server-side web search
"""

from __future__ import annotations

import os
import sys


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


class AnthropicLLM:
    """Claude via the official Anthropic SDK. Streams (long outputs), caches the
    system prompt + dossier prefix, uses adaptive thinking."""

    def __init__(self, model: str = "claude-opus-4-8"):
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = model

    def generate(self, system: str, user: str, max_tokens: int = 32000) -> str:
        with self.client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            system=[
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user}],
        ) as stream:
            message = stream.get_final_message()
        return "".join(b.text for b in message.content if b.type == "text")

    def research(self, prompt: str, max_tokens: int = 64000, max_searches: int = 30) -> str:
        """Run the research prompt with Anthropic's server-side web search tool.
        Handles pause_turn continuation for long server-tool loops."""
        tools = [
            {"type": "web_search_20260209", "name": "web_search", "max_uses": max_searches}
        ]
        messages = [{"role": "user", "content": prompt}]
        text_parts: list[str] = []
        for _ in range(8):  # pause_turn continuation cap
            with self.client.messages.stream(
                model=self.model,
                max_tokens=max_tokens,
                thinking={"type": "adaptive"},
                output_config={"effort": "high"},
                tools=tools,
                messages=messages,
            ) as stream:
                response = stream.get_final_message()
            if response.stop_reason == "pause_turn":
                messages = [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": response.content},
                ]
                log("  ...research paused by server tool loop, resuming")
                continue
            text_parts.extend(b.text for b in response.content if b.type == "text")
            break
        return "".join(text_parts)


class OpenAICompatLLM:
    """GLM 5.2 (or any OpenAI-compatible endpoint). Defaults to Z.ai's international
    endpoint; point base_url at https://openrouter.ai/api/v1 with model 'z-ai/glm-5.2'
    for the cheaper routed option."""

    def __init__(
        self,
        model: str = "glm-5.2",
        base_url: str = "https://api.z.ai/api/paas/v4",
        api_key_env: str = "GLM_API_KEY",
    ):
        from openai import OpenAI

        api_key = os.environ.get(api_key_env) or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(f"Set {api_key_env} for the GLM/OpenAI-compatible provider")
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def generate(self, system: str, user: str, max_tokens: int = 32000) -> str:
        stream = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            stream=True,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        parts: list[str] = []
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                parts.append(chunk.choices[0].delta.content)
        return "".join(parts)


def make_llm(cfg: dict):
    provider = cfg.get("provider", "glm")
    if provider == "anthropic":
        return AnthropicLLM(model=cfg.get("model", "claude-opus-4-8"))
    if provider in ("glm", "openai_compat"):
        return OpenAICompatLLM(
            model=cfg.get("model", "glm-5.2"),
            base_url=cfg.get("base_url", "https://api.z.ai/api/paas/v4"),
            api_key_env=cfg.get("api_key_env", "GLM_API_KEY"),
        )
    raise ValueError(f"Unknown LLM provider: {provider}")
