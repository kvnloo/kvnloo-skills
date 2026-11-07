"""Adapter registry. `get("chatgpt")` returns a fresh adapter instance."""
from __future__ import annotations

from .base import Adapter
from .chatgpt import ChatGPT
from .deepseek import DeepSeek

REGISTRY = {"chatgpt": ChatGPT, "deepseek": DeepSeek}


def get(name: str) -> Adapter:
    try:
        return REGISTRY[name]()
    except KeyError:
        raise KeyError(f"unknown adapter {name!r}; known: {sorted(REGISTRY)}") from None


def names() -> list[str]:
    return sorted(REGISTRY)


__all__ = ["Adapter", "ChatGPT", "DeepSeek", "REGISTRY", "get", "names"]
