"""
BaseAgent — fully rewritten for LangChain 1.x.

Key LangChain 1.x advances used:
  - ChatAnthropic / ChatOpenAI (langchain provider wrappers)
  - ChatPromptTemplate + SystemMessage / HumanMessage
  - LCEL pipe chains:  prompt | model | parser
  - StrOutputParser / JsonOutputParser from langchain_core.output_parsers
  - with_structured_output(PydanticModel) for type-safe responses
  - RunnableLambda / RunnableConfig for composable steps
  - Built-in retry via .with_retry() on any Runnable
"""
from __future__ import annotations

import hashlib
import json
import re
from abc import ABC, abstractmethod
from typing import Any, TypeVar

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnableConfig
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from migration_platform.config.settings import get_settings
from migration_platform.core.logging import get_logger
from migration_platform.workflows.state import MigrationState

T = TypeVar("T", bound=BaseModel)


class BaseAgent(ABC):
    """
    Abstract base for all 9 migration agents.

    LangChain 1.x patterns used:
      • ChatAnthropic / ChatOpenAI as LLM backends
      • LCEL chains (prompt | model | parser) for composable invocation
      • with_structured_output() for Pydantic-typed responses
      • .with_retry() on chains — no manual tenacity decorators needed
      • RunnableLambda for inline transformations
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._logger   = get_logger(self.__class__.__name__)

        # ── Primary model: Claude via LangChain provider ──────────────────
        self._claude: ChatAnthropic = ChatAnthropic(
            model=self._settings.primary_model,
            api_key=self._settings.anthropic_api_key,       # type: ignore[arg-type]
            max_tokens=self._settings.max_tokens,
            temperature=self._settings.temperature,
        )

        # ── Validation model: GPT-4o via LangChain provider ───────────────
        self._gpt4o: ChatOpenAI = ChatOpenAI(
            model=self._settings.validation_model,
            api_key=self._settings.openai_api_key,          # type: ignore[arg-type]
            max_tokens=self._settings.max_tokens,
            temperature=self._settings.temperature,
        )

    # ── Abstract interface ────────────────────────────────────────────────

    @abstractmethod
    def run(self, state: MigrationState) -> MigrationState:
        """Execute agent logic. Return updated state."""

    # ── LCEL chain builders ───────────────────────────────────────────────

    def _text_chain(self, system: str) -> Any:
        """
        Build a simple LCEL text chain:
            prompt | claude | StrOutputParser
        Chain has built-in retry (3 attempts, exponential backoff).
        """
        prompt = ChatPromptTemplate.from_messages([
            ("system", system),
            ("human",  "{input}"),
        ])
        chain = prompt | self._claude | StrOutputParser()
        return chain.with_retry(stop_after_attempt=3, wait_exponential_jitter=True)

    def _json_chain(self, system: str) -> Any:
        """
        LCEL chain that parses the LLM response as JSON.
            prompt | claude | JsonOutputParser
        Falls back to empty dict on parse failure.
        """
        prompt = ChatPromptTemplate.from_messages([
            ("system", system + "\n\nIMPORTANT: Respond with valid JSON only. No markdown fences."),
            ("human",  "{input}"),
        ])
        chain = (
            prompt
            | self._claude
            | RunnableLambda(self._strip_fences)
            | JsonOutputParser()
        )
        return chain.with_retry(stop_after_attempt=3, wait_exponential_jitter=True)

    def _structured_chain(self, system: str, schema: type[T], model: str = "claude") -> Any:
        """
        LCEL chain with structured output via with_structured_output().

        LangChain 1.x feature: the LLM is forced to return a validated
        Pydantic object — no manual JSON parsing needed.

        Args:
            system:  System prompt text.
            schema:  Pydantic model class for structured output.
            model:   "claude" (default) or "gpt4o".
        """
        llm = self._claude if model == "claude" else self._gpt4o
        structured_llm = llm.with_structured_output(schema)

        prompt = ChatPromptTemplate.from_messages([
            ("system", system),
            ("human",  "{input}"),
        ])
        chain = prompt | structured_llm
        return chain.with_retry(stop_after_attempt=3, wait_exponential_jitter=True)

    def _parallel_validation_chain(self, system: str) -> Any:
        """
        LangChain 1.x RunnableParallel — run Claude and GPT-4o simultaneously.

        Returns: {"claude": dict, "gpt4o": dict}
        """
        from langchain_core.runnables import RunnableParallel

        prompt = ChatPromptTemplate.from_messages([
            ("system", system + "\n\nRespond with JSON only. No markdown fences."),
            ("human",  "{input}"),
        ])
        parse = RunnableLambda(self._strip_fences) | JsonOutputParser()

        claude_chain = (prompt | self._claude | parse).with_retry(stop_after_attempt=3)
        gpt4o_chain  = (prompt | self._gpt4o  | parse).with_retry(stop_after_attempt=3)

        return RunnableParallel(claude=claude_chain, gpt4o=gpt4o_chain)

    # ── Convenience invoke wrappers ───────────────────────────────────────

    def _call_text(self, system: str, user_input: str) -> str:
        """Invoke a text chain and return string output."""
        cache_key = self._cache_key(system + user_input)
        # Check LLM response cache (diskcache via storage)
        try:
            from migration_platform.storage.cache_store import CacheStore
            _cache = CacheStore()
            cached = _cache.get_llm_response(cache_key)
            if cached:
                return cached
        except Exception:
            _cache = None

        result: str = self._text_chain(system).invoke({"input": user_input})

        try:
            if _cache:
                _cache.set_llm_response(cache_key, result)
        except Exception:
            pass
        return result

    def _call_json(self, system: str, user_input: str) -> dict[str, Any]:
        """Invoke a JSON chain and return parsed dict."""
        try:
            result = self._json_chain(system).invoke({"input": user_input})
            return result if isinstance(result, dict) else {}
        except Exception as exc:
            self._logger.error("JSON chain failed", error=str(exc))
            return {}

    def _call_structured(
        self,
        system: str,
        user_input: str,
        schema: type[T],
        model: str = "claude",
    ) -> T | None:
        """Invoke a structured-output chain and return a Pydantic instance."""
        try:
            return self._structured_chain(system, schema, model).invoke({"input": user_input})
        except Exception as exc:
            self._logger.error("Structured chain failed", schema=schema.__name__, error=str(exc))
            return None

    def _call_parallel_validation(
        self, system: str, user_input: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Run parallel validation and return (claude_result, gpt4o_result)."""
        try:
            results = self._parallel_validation_chain(system).invoke({"input": user_input})
            return results.get("claude", {}), results.get("gpt4o", {})
        except Exception as exc:
            self._logger.error("Parallel validation failed", error=str(exc))
            return {}, {}

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _strip_fences(msg: Any) -> str:
        """Strip markdown code fences from LLM output before JSON parsing."""
        text = msg.content if hasattr(msg, "content") else str(msg)
        return re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())

    @staticmethod
    def _cache_key(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    # ── Legacy shim (for agents not yet fully migrated) ───────────────────

    def _call_llm(self, system: str, user: str) -> str:
        """Backward-compat shim — delegates to _call_text."""
        return self._call_text(system, user)

    def _call_llm_json(self, system: str, user: str) -> dict[str, Any]:
        """Backward-compat shim — delegates to _call_json."""
        return self._call_json(system, user)
