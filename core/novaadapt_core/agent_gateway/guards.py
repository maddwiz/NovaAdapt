from __future__ import annotations

import os

FORBIDDEN_LLM_KEYS = [
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "MOONSHOT_API_KEY",
]


def assert_no_llm_env() -> None:
    for key in FORBIDDEN_LLM_KEYS:
        if os.getenv(key):
            raise RuntimeError(
                f"{key} is present in NovaAgent gateway process. "
                "Gateway must not own LLM credentials."
            )
