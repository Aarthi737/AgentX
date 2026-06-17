"""
AgentX — LLM Client (Gemini via google-genai)
Drop-in replacement for the old Groq client.
Same interface — no changes needed in agents.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, Dict, List, Optional

import google.generativeai as genai

from config.settings import settings
from core.logging import get_logger

logger = get_logger(__name__)

GEMINI_MODEL = "gemini-2.0-flash" 

class GroqMessage:
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
    def __init__(self):
        self.client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        self.temperature = getattr(settings, 'groq_temperature', 0.1)
        self.max_tokens = getattr(settings, 'groq_max_tokens', 2048)

    async def complete(
        self,
        messages: List[Dict],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        user_parts = [m["content"] for m in messages if m["role"] == "user"]

        system_text = "\n".join(system_parts)
        user_text = "\n".join(user_parts)

        if json_mode:
            user_text += "\n\nRespond with ONLY a valid JSON object, no markdown, no explanation."

        full_prompt = f"{system_text}\n\n{user_text}" if system_text else user_text

        config = types.GenerateContentConfig(
            temperature=temperature if temperature is not None else self.temperature,
            max_output_tokens=max_tokens or self.max_tokens,
        )

        try:
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=GEMINI_MODEL,
                contents=full_prompt,
                config=config,
            )
            return response.text or ""
        except Exception as exc:
            logger.warning("gemini_completion_failed", error=str(exc))
            raise

    async def complete_json(
        self,
        messages: List[Dict],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict:
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


_groq_client_instance: Optional[GroqClient] = None


def get_groq() -> GroqClient:
    global _groq_client_instance
    if _groq_client_instance is None:
        _groq_client_instance = GroqClient()
    return _groq_client_instance