"""Real chat models through LangChain: OpenAI (GPT-4o-mini) and Google Gemini Flash.

Both are asked for a JSON object (OpenAI JSON mode / Gemini ``application/json``) and the answer is parsed
here; callers validate it against their own schema. Install with:
``pip install "shopsathi-ai[llm]"`` (or the ``openai`` / ``gemini`` extra).

Tool calling: the shop tools (search products, check stock, get delivery charge) are run by the engine from
the understood intent, so the model never has to choose tools; see ``shopsathi_ai.tools``.
"""

import json
import re
from typing import Any

from shopsathi_ai.providers.base import LLMProvider, LLMProviderError, LLMResult

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_TIMEOUT_SECONDS = 20  # NFR-01: a reply should arrive within 8 seconds; fail fast instead of hanging


def _text_of(content: Any) -> str:
    """LangChain message content is a string, or a list of parts for some models."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p if isinstance(p, str) else str(p.get("text", "")) for p in content)
    return str(content)


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = _FENCE.sub("", text.strip())
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise
        data = json.loads(cleaned[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("the model did not return a JSON object")
    return data


class LangChainJSONProvider(LLMProvider):
    def __init__(self, chat_model: Any, name: str, model: str) -> None:
        self._chat = chat_model
        self.name = name
        self.model = model

    def generate_json_with_usage(self, system_prompt: str, user_prompt: str, *, task: str = "generic") -> LLMResult:
        from langchain_core.messages import HumanMessage, SystemMessage

        try:
            message = self._chat.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
        except Exception as e:  # network, auth, rate limit, safety block ...
            raise LLMProviderError(f"{self.name} request failed: {e.__class__.__name__}") from e
        try:
            data = parse_json_object(_text_of(message.content))
        except (ValueError, json.JSONDecodeError):
            # Return an empty object: the caller's schema validation turns this into a retry.
            data = {}
        usage = getattr(message, "usage_metadata", None) or {}
        return LLMResult(
            data=data,
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            provider=self.name,
            model=self.model,
        )


def build_openai(api_key: str, model: str) -> LangChainJSONProvider:
    if not api_key:
        raise LLMProviderError("OPENAI_API_KEY is not set")
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as e:
        raise LLMProviderError('Install the OpenAI chat model: pip install "shopsathi-ai[openai]"') from e
    chat = ChatOpenAI(
        model=model,
        api_key=api_key,
        temperature=0.2,
        timeout=_TIMEOUT_SECONDS,
        max_retries=1,
        model_kwargs={"response_format": {"type": "json_object"}},
    )
    return LangChainJSONProvider(chat, "openai", model)


def build_gemini(api_key: str, model: str) -> LangChainJSONProvider:
    if not api_key:
        raise LLMProviderError("GEMINI_API_KEY is not set")
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError as e:
        raise LLMProviderError('Install the Gemini chat model: pip install "shopsathi-ai[gemini]"') from e
    chat = ChatGoogleGenerativeAI(
        model=model,
        google_api_key=api_key,
        temperature=0.2,
        response_mime_type="application/json",
        timeout=_TIMEOUT_SECONDS,
        max_retries=1,
    )
    return LangChainJSONProvider(chat, "gemini", model)
