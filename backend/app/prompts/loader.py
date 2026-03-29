import json
from functools import lru_cache
from pathlib import Path
from typing import Any


PROMPTS_PATH = Path(__file__).with_name("prompts.json")


@lru_cache(maxsize=1)
def load_prompts() -> dict[str, Any]:
    with PROMPTS_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def _normalize_prompt(value: Any) -> str:
    if isinstance(value, list):
        if not all(isinstance(item, str) for item in value):
            raise TypeError("Prompt list values must contain only strings.")
        return "\n".join(value)
    if isinstance(value, str):
        return value
    raise TypeError(f"Prompt value must be a string or list of strings, got {type(value).__name__}.")


def get_prompt(path: str) -> str:
    current: Any = load_prompts()
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            raise KeyError(f"Prompt path not found: {path}")
        current = current[key]
    return _normalize_prompt(current)


def render_prompt(path: str, **kwargs: Any) -> str:
    return get_prompt(path).format(**kwargs)
