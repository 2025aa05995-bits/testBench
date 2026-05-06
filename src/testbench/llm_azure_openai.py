"""Backward-compatible alias; prefer ``testbench.llm_chat.llm_chat_to_plan``."""

from .llm_chat import llm_chat_to_plan as azure_openai_chat_to_plan

__all__ = ["azure_openai_chat_to_plan"]
