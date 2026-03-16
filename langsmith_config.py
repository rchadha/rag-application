import os


def is_langsmith_enabled() -> bool:
    tracing = os.getenv("LANGSMITH_TRACING", "false").lower()
    return tracing in {"1", "true", "yes", "on"} and bool(os.getenv("LANGSMITH_API_KEY"))


def get_langsmith_project(default_project: str) -> str:
    return os.getenv("LANGSMITH_PROJECT", default_project)
