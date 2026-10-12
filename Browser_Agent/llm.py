import os
import logging
from dotenv import load_dotenv
from pathlib import Path

from browser_use.llm import ChatGoogle, ChatOllama

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logger = logging.getLogger(__name__)

# gemini-flash-lite-latest: highest free-tier RPM (low cost, great for browser-use)
# gemini-2.5-flash: more capable but only 5 RPM on free tier
_GOOGLE_MODEL_DEFAULT = "gemini-flash-lite-latest"
_OLLAMA_MODEL_DEFAULT = "qwen2.5:7b"


def _make_google_llm():
    model = os.getenv("GOOGLE_MODEL", _GOOGLE_MODEL_DEFAULT)
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GOOGLE_API_KEY is not set in .env")
    return ChatGoogle(model=model, api_key=api_key, temperature=0.2)


def _make_ollama_llm():
    model = os.getenv("OLLAMA_MODEL", _OLLAMA_MODEL_DEFAULT)
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    return ChatOllama(model=model, base_url=base_url)


def get_llm():
    """
    Returns primary LLM for browser-use Agent.

    Default: gemini-flash-lite-latest (high free-tier RPM, fast)
    Override via env vars:
      GOOGLE_MODEL  - change the Gemini model
      LLM_PROVIDER=ollama - force local Ollama
    """
    provider = os.getenv("LLM_PROVIDER", "google").lower()
    if provider == "ollama":
        logger.info("[LLM] Ollama selected via LLM_PROVIDER env var")
        return _make_ollama_llm()

    try:
        llm = _make_google_llm()
        logger.info("[LLM] Google Gemini: %s", os.getenv("GOOGLE_MODEL", _GOOGLE_MODEL_DEFAULT))
        return llm
    except Exception as e:
        logger.warning("[LLM] Gemini init failed (%s) - using Ollama as primary", e)
        return _make_ollama_llm()


def get_fallback_llm():
    """
    Returns fallback LLM passed as Agent(fallback_llm=...).
    browser-use switches to this automatically when the primary LLM fails mid-run.
    Returns None if Ollama is not available (agent retries primary instead).
    """
    try:
        llm = _make_ollama_llm()
        logger.info("[LLM] Ollama fallback ready: %s", os.getenv("OLLAMA_MODEL", _OLLAMA_MODEL_DEFAULT))
        return llm
    except Exception as e:
        logger.warning("[LLM] Ollama not available for fallback: %s", e)
        return None
