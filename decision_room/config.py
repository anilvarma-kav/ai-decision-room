"""Server-owned model allowlist and explicit live-mode configuration."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    model: str
    available: bool


def providers() -> dict[str, Provider]:
    return {
        "openai": Provider(
            "openai",
            "OpenAI",
            os.getenv("MODEL_OPENAI", "openai/gpt-4.1-mini"),
            bool(os.getenv("OPENAI_API_KEY")),
        ),
        "anthropic": Provider(
            "anthropic",
            "Anthropic",
            os.getenv("MODEL_ANTHROPIC", "anthropic/claude-sonnet-4-5-20250929"),
            bool(os.getenv("ANTHROPIC_API_KEY")),
        ),
        "gemini": Provider(
            "gemini",
            "Google",
            os.getenv("MODEL_GEMINI", "gemini/gemini-2.5-flash"),
            bool(os.getenv("GEMINI_API_KEY")),
        ),
        "ollama": Provider(
            "ollama",
            "Ollama",
            os.getenv("MODEL_OLLAMA", "ollama_chat/llama3.2"),
            os.getenv("ENABLE_OLLAMA") == "1",
        ),
    }


def live_enabled() -> bool:
    return os.getenv("ENABLE_LIVE") == "1"
