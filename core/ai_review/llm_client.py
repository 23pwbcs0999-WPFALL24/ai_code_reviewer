"""
core/ai_review/llm_client.py
─────────────────────────────
Unified LLM client that supports multiple API providers.
Switching providers is a one-line change in the .env file.

Supported providers:
  - Groq      (free tier, very fast, Llama 3 / Mixtral models)
  - Gemini    (Google, free tier available)
  - OpenAI    (paid, highest quality)

All providers implement the same interface:
  call(system_prompt, user_prompt) → response_text
"""

from __future__ import annotations
import json
import time
from typing import Optional

from config.settings import settings


class LLMError(Exception):
    """Raised when the LLM API call fails."""
    pass


class LLMClient:
    """
    Provider-agnostic LLM client.
    Instantiate once and call `complete()` to get a response.
    """

    def __init__(self):
        self.provider = settings.LLM_PROVIDER
        self.model    = settings.active_model
        self.api_key  = settings.active_api_key

        # Validate configuration
        if not settings.llm_available:
            raise LLMError(
                f"No valid API key found for provider '{self.provider}'. "
                "Please set the correct key in your .env file."
            )

    def complete(
        self,
        user_prompt: str,
        system_prompt: str = "",
        temperature: float = 0.2,
        max_tokens: int = 4096,
        retries: int = 2,
    ) -> str:
        """
        Send a prompt to the configured LLM and return the response text.

        Args:
            user_prompt:   The main instruction / content for the LLM
            system_prompt: Optional system-level instruction
            temperature:   Creativity level (0 = deterministic, 1 = creative)
            max_tokens:    Maximum tokens to generate
            retries:       How many times to retry on transient errors

        Returns:
            The LLM's response as a plain string.

        Raises:
            LLMError: If the API call fails after all retries.
        """
        last_error: Optional[Exception] = None

        for attempt in range(retries + 1):
            try:
                if self.provider == "groq":
                    return self._call_groq(user_prompt, system_prompt, temperature, max_tokens)
                elif self.provider == "gemini":
                    return self._call_gemini(user_prompt, system_prompt, temperature, max_tokens)
                elif self.provider == "openai":
                    return self._call_openai(user_prompt, system_prompt, temperature, max_tokens)
                else:
                    raise LLMError(f"Unknown provider: '{self.provider}'")

            except LLMError:
                raise   # Don't retry on configuration errors
            except Exception as exc:
                last_error = exc
                if attempt < retries:
                    wait_sec = 2 ** attempt   # Exponential backoff: 1s, 2s
                    time.sleep(wait_sec)

        raise LLMError(
            f"LLM API call failed after {retries + 1} attempts. "
            f"Last error: {last_error}"
        )

    # ── Groq ──────────────────────────────────────────────────────────────────

    def _call_groq(
        self,
        user_prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        try:
            from groq import Groq
        except ImportError:
            raise LLMError("groq package not installed. Run: pip install groq")

        client = Groq(api_key=self.api_key)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return response.choices[0].message.content or ""

    # ── Gemini ────────────────────────────────────────────────────────────────

    def _call_gemini(
        self,
        user_prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        try:
            import google.generativeai as genai
        except ImportError:
            raise LLMError(
                "google-generativeai package not installed. "
                "Run: pip install google-generativeai"
            )

        genai.configure(api_key=self.api_key)

        generation_config = {
            "temperature":     temperature,
            "max_output_tokens": max_tokens,
        }

        # Combine system prompt with user prompt (Gemini handles it differently)
        full_prompt = user_prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{user_prompt}"

        model_name = self._resolve_gemini_model(genai, self.model)

        model = genai.GenerativeModel(
            model_name=model_name,
            generation_config=generation_config,
        )

        try:
            response = model.generate_content(full_prompt)
            return response.text or ""
        except Exception as exc:
            msg = str(exc).lower()
            # If the configured model is unavailable, try a second-pass fallback
            # from available models that support generateContent.
            if "not found" in msg or "not supported" in msg:
                fallback_model = self._resolve_gemini_model(genai, "")
                if fallback_model != model_name:
                    model = genai.GenerativeModel(
                        model_name=fallback_model,
                        generation_config=generation_config,
                    )
                    response = model.generate_content(full_prompt)
                    self.model = fallback_model
                    return response.text or ""
            raise

    def _resolve_gemini_model(self, genai_module, preferred_model: str) -> str:
        """
        Resolve a Gemini model that supports generateContent.
        Falls back to available flash/pro models if preferred model is invalid.
        """
        preferred = (preferred_model or "").strip()
        # Fast path for common valid names; keeps behavior deterministic.
        common_candidates = [
            preferred,
            "gemini-2.0-flash",
            "gemini-2.5-flash",
            "gemini-1.5-flash-latest",
            "gemini-1.5-pro-latest",
        ]
        common_candidates = [name for name in common_candidates if name]

        available: list[str] = []
        try:
            for model in genai_module.list_models():
                methods = getattr(model, "supported_generation_methods", []) or []
                if "generateContent" in methods:
                    name = getattr(model, "name", "")
                    if name.startswith("models/"):
                        name = name.split("/", 1)[1]
                    if name:
                        available.append(name)
        except Exception:
            # If listing fails, return preferred and let the caller surface the API error.
            return preferred or "gemini-2.0-flash"

        if not available:
            return preferred or "gemini-2.0-flash"

        # 1) Preferred exact match
        if preferred and preferred in available:
            return preferred

        # 2) Any known good candidate present
        for candidate in common_candidates:
            if candidate in available:
                return candidate

        # 3) First flash model (usually cheapest/fastest)
        for name in available:
            if "flash" in name:
                return name

        # 4) First available generation-capable model
        return available[0]

    # ── OpenAI ────────────────────────────────────────────────────────────────

    def _call_openai(
        self,
        user_prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        try:
            from openai import OpenAI
        except ImportError:
            raise LLMError("openai package not installed. Run: pip install openai")

        client = OpenAI(api_key=self.api_key)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return response.choices[0].message.content or ""


# ─── Convenience factory ──────────────────────────────────────────────────────

def get_llm_client() -> Optional[LLMClient]:
    """
    Try to create an LLMClient.
    Returns None (without raising) if no API key is configured.
    This is used by the reviewer to gracefully fall back to static-only mode.
    """
    if not settings.llm_available:
        return None
    try:
        return LLMClient()
    except Exception:
        return None
