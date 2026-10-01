from pathlib import Path

from dotenv import dotenv_values
import os


def load_environment(root: Path) -> None:
    """Read only benchmark credentials, without shell expansion or parent search."""
    values = dotenv_values(root / ".env", interpolate=False)
    for key in ("GEMINI_API_KEY", "OPENAI_API_KEY"):
        if values.get(key) and not os.environ.get(key):
            os.environ[key] = values[key]
