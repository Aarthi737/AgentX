"""
AgentX — Gemini LLM Client
Provides a Gemini-compatible language client for backend agents.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any, Dict, List, Optional

import google.generativeai as genai

from config.settings import settings
from core.logging import get_logger

logger = get_logger(__name__)

GEMINI_MODEL = "gemini-1.5-flash"


class GeminiMessage:
    @staticmethod
    def system(content: str) -> Dict[str, str]:
        return {"role": "system", "content": content}

    @staticmethod
    def user(content: str) -> Dict[str, str]:
        return {"role": "user", "content": content}

    @staticmethod
    def assistant(content: str) -> Dict[str, str]:
        return {"role": "assistant", "content": content}


class GeminiClient:
    def __init__(self):
        api_key = settings.GOOGLE_API_KEY

        if not api_key:
            raise ValueError("GOOGLE_API_KEY is missing")

        genai.configure(api_key=api_key)

        self.temperature = getattr(settings, "google_temperature", 0.1)
        self.max_tokens = getattr(settings, "google_max_tokens", 2048)

        self.model = genai.GenerativeModel(GEMINI_MODEL)

    async def complete(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        if temperature is None:
            temperature = self.temperature
        if max_tokens is None:
            max_tokens = self.max_tokens

        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        user_parts = [m["content"] for m in messages if m["role"] == "user"]

        system_text = "\n".join(system_parts)
        user_text = "\n".join(user_parts)

        if json_mode:
            user_text += "\n\nRespond ONLY in valid JSON."

        full_prompt = f"{system_text}\n\n{user_text}" if system_text else user_text

        try:
            response = await asyncio.to_thread(
                self.model.generate_content,
                full_prompt,
            )
            return getattr(response, "text", "") or ""

        except Exception as exc:
            logger.warning("gemini_completion_failed", error=str(exc))
            raise

    async def complete_json(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
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
        messages = [
            GeminiMessage.system(system_prompt),
            GeminiMessage.user(user_prompt),
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
    ) -> Dict[str, Any]:
        messages = [
            GeminiMessage.system(system_prompt),
            GeminiMessage.user(user_prompt),
        ]
        return await self.complete_json(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )


def _parse_json_safe(text: str) -> Dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", cleaned)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        logger.warning("gemini_json_parse_failed", raw_text=text[:500])
        return {"error": "json_parse_failed", "raw": text}


_gemini_client_instance: Optional[GeminiClient] = None


def get_gemini() -> GeminiClient:
    global _gemini_client_instance
    if _gemini_client_instance is None:
        _gemini_client_instance = GeminiClient()
    return _gemini_client_instance
