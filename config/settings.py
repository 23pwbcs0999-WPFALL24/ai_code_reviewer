"""
config/settings.py
──────────────────
Centralised application configuration.
All settings are loaded from environment variables (via .env file).
Defaults are provided so the app works even without a .env file.
"""

import os
from dotenv import load_dotenv

# Load .env file if it exists (silently ignored if not present)
load_dotenv()


class Settings:
    """
    Single source of truth for all app configuration.
    Access via the module-level `settings` singleton below.
    """

    # ── App Info ──────────────────────────────────────────────────────────────
    APP_TITLE: str = os.getenv("APP_TITLE", "AI Code Reviewer")
    APP_VERSION: str = "1.0.0"
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "5"))
    MAX_CODE_LINES: int = int(os.getenv("MAX_CODE_LINES", "2000"))

    # ── LLM Provider ─────────────────────────────────────────────────────────
    # Supported: "groq" | "gemini" | "openai" | "none"
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "groq").lower()

    # ── Groq ──────────────────────────────────────────────────────────────────
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    # ── Gemini ────────────────────────────────────────────────────────────────
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    # ── OpenAI ────────────────────────────────────────────────────────────────
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # ── Supported Languages ───────────────────────────────────────────────────
    # Extension → display name mapping.
    # Add new languages here when you extend the system.
    SUPPORTED_LANGUAGES: dict = {
        ".py": "Python",
        # Future: ".js": "JavaScript", ".ts": "TypeScript", ".java": "Java"
    }

    @property
    def llm_available(self) -> bool:
        """Returns True if a valid LLM provider and API key are configured."""
        provider = self.LLM_PROVIDER
        if provider == "groq":
            return bool(self.GROQ_API_KEY and self.GROQ_API_KEY != "your_groq_api_key_here")
        if provider == "gemini":
            return bool(self.GEMINI_API_KEY and self.GEMINI_API_KEY != "your_gemini_api_key_here")
        if provider == "openai":
            return bool(self.OPENAI_API_KEY and self.OPENAI_API_KEY != "your_openai_api_key_here")
        return False

    @property
    def active_api_key(self) -> str:
        """Returns the API key for the currently configured provider."""
        mapping = {
            "groq": self.GROQ_API_KEY,
            "gemini": self.GEMINI_API_KEY,
            "openai": self.OPENAI_API_KEY,
        }
        return mapping.get(self.LLM_PROVIDER, "")

    @property
    def active_model(self) -> str:
        """Returns the model name for the currently configured provider."""
        mapping = {
            "groq": self.GROQ_MODEL,
            "gemini": self.GEMINI_MODEL,
            "openai": self.OPENAI_MODEL,
        }
        return mapping.get(self.LLM_PROVIDER, "")


# Module-level singleton — import this everywhere
settings = Settings()
