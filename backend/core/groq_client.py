"""
AgentX — Groq LLM Client
Centralised client for all Groq Llama 3.3 70B calls.
Features: structured retry with exponential backoff, token counting,
rate-limit detection, prompt template rendering, JSON parsing.
Used by: Agents 3, 4, 5, 6, 7, 8.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, Dict, List, Optional

import httpx
from groq import AsyncGroq, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config.settings import settings
from core.logging import get_logger

logger = get_logger(__name__)

# Global async Groq client (initialised once)
_groq_client: Optional[AsyncGroq] = None


def get_groq_client() -> AsyncGroq:
    global _groq_client
    if _groq_client is None:
        _groq_client = AsyncGroq(api_key=settings.groq_api_key)
    return _groq_client


class GroqMessage:
    """Helper to build message lists for Groq chat completions."""

    @staticmethod
    def system(content: str) -> Dict:
        return {"role": "system", "content": content}

    @staticmethod
    def user(content: str) -> Dict:
        return {"role": "user", "content": content}

    @staticmethod
    def assistant(content: str) -> Dict:
        return {"role": "assistant", "content": content}


class GroqClient:
    """
    Wrapper around AsyncGroq with retry, JSON extraction, and logging.
    Instantiate once per agent or use the module-level singleton helpers.
    """

    def __init__(self):
        self.client = get_groq_client()
        self.model = settings.groq_model
        self.max_tokens = settings.groq_max_tokens
        self.temperature = settings.groq_temperature

    @retry(
        retry=retry_if_exception_type((RateLimitError, httpx.TimeoutException)),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        stop=stop_after_attempt(settings.groq_max_retries),
        reraise=True,
    )
    async def complete(
        self,
        messages: List[Dict],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        """
        Send a chat completion request to Groq.
        Returns the text content of the first choice.
        """
        t_start = time.monotonic()
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = await self.client.chat.completions.create(**kwargs)
        duration = (time.monotonic() - t_start) * 1000

        content = response.choices[0].message.content or ""
        logger.debug(
            "groq_completion",
            model=self.model,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            duration_ms=round(duration),
        )
        return content

    async def complete_json(
        self,
        messages: List[Dict],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict:
        """
        Request JSON output from Groq and parse it.
        Falls back to regex extraction if the model wraps JSON in markdown fences.
        """
        raw = await self.complete(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
        return _parse_json_safe(raw)

    async def complete_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        """Convenience wrapper for system + user prompt pair."""
        messages = [
            GroqMessage.system(system_prompt),
            GroqMessage.user(user_prompt),
        ]
        return await self.complete(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )

    async def complete_structured_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict:
        """System + user → parsed JSON dict."""
        messages = [
            GroqMessage.system(system_prompt),
            GroqMessage.user(user_prompt),
        ]
        return await self.complete_json(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )


def _parse_json_safe(text: str) -> Dict:
    """Parse JSON from LLM output, handling markdown code fences."""
    # Strip ```json ... ``` or ``` ... ``` wrappers
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Attempt to find JSON object/array within the text
        match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", cleaned)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        logger.warning("groq_json_parse_failed", raw_text=text[:500])
        return {"error": "json_parse_failed", "raw": text}


# Module-level singleton
_groq_client_instance: Optional[GroqClient] = None


def get_groq() -> GroqClient:
    """Return module-level GroqClient singleton."""
    global _groq_client_instance
    if _groq_client_instance is None:
        _groq_client_instance = GroqClient()
    return _groq_client_instance
