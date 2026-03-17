"""
CodeGenAgent — Phase B / Step 2.

LangChain 1.x advances:
  - LCEL chains per output type (React / Spring Boot)
  - ChatPromptTemplate with rich variable injection
  - StrOutputParser for code output
  - Parallel execution via ThreadPoolExecutor (Send handles module fan-out at graph level)
  - with_retry() on every chain — no manual tenacity needed
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from migration_platform.agents.base import BaseAgent

# Global semaphore — limits concurrent Claude API calls across all parallel
# Send workers.  With _MAX_PARALLEL_MODULES=6 and 2 LLM calls per worker,
# this caps concurrent Anthropic requests at 4×2=8, well within rate limits.
_CODEGEN_SEMAPHORE = threading.Semaphore(4)
from migration_platform.codegen.context_builder import ContextBuilder
from migration_platform.codegen.gradle_scaffold import GradleScaffold
from migration_platform.codegen.react_generator import ReactGenerator
from migration_platform.codegen.spring_generator import SpringGenerator
from migration_platform.config.settings import get_settings
from migration_platform.storage.state_store import StateStore
from migration_platform.workflows.state import MigrationState

_REACT_SYSTEM = """
You are an expert React 18 + TypeScript developer migrating a JSP page to modern React.

Given JSP source chunks and the REST API contract, generate:
1. A functional .tsx component with useState, useEffect, useCallback hooks
2. Axios API calls replacing all JSP scriptlet backend interactions
3. TypeScript interfaces for all data types
4. Loading state + error state handling
5. Form validation if the JSP has a form

Rules:
- Functional components only — no class components
- No JSP constructs (no JSTL, no EL expressions)
- No inline styles — use CSS Modules
- All API calls must use endpoints from the provided REST contract
- Export default the component

Output ONLY the .tsx file content. No explanation, no markdown fences.
""".strip()

_SPRING_SYSTEM = """
You are an expert Spring Boot 3.3 + Java 21 developer migrating a Java Servlet to modern Spring Boot.

Given servlet chunks, SOAP dependencies, and JDBC-to-JPA mappings, generate:
1. @RestController with correct @RequestMapping, @GetMapping, @PostMapping
2. @Service class with extracted business logic
3. JpaRepository interface for each database table
4. @Entity classes with @Id, @Column, @GeneratedValue
5. SOAP adapter or Spring WS client per the specified migration option

Rules:
- Gradle syntax for any dependency references (NOT Maven)
- Constructor injection (never @Autowired field injection)
- @Slf4j for logging
- ResponseEntity<T> from all controller methods
- Jakarta Bean Validation on DTOs

Output a JSON array: [{"path": "src/...", "content": "..."}]
""".strip()


class CodeGenAgent(BaseAgent):
    """
    Generates React components and Spring Boot files.

    Receives module-scoped state via LangGraph Send API (one invocation per module).
    Each invocation assembles a RAG context and invokes a typed LCEL chain.
    """

    def __init__(
        self,
        context_builder: ContextBuilder,
        state_store: StateStore,
    ) -> None:
        super().__init__()
        self._ctx     = context_builder
        self._ss      = state_store
        self._react   = ReactGenerator(self)
        self._spring  = SpringGenerator(self)
        self._gradle  = GradleScaffold()

        # ── LCEL chains with built-in retry ──────────────────────────────
        self._react_chain = (
            ChatPromptTemplate.from_messages([
                ("system", _REACT_SYSTEM),
                ("human", "{context}"),
            ])
            | self._claude
            | StrOutputParser()
        ).with_retry(stop_after_attempt=3, wait_exponential_jitter=True)

        self._spring_chain = (
            ChatPromptTemplate.from_messages([
                ("system", _SPRING_SYSTEM),
                ("human", "{context}"),
            ])
            | self._claude
            | StrOutputParser()
        ).with_retry(stop_after_attempt=3, wait_exponential_jitter=True)

    def run(self, state: MigrationState) -> MigrationState:
        """
        Handle one module (called per Send from dispatch_codegen).
        Generates React + Spring Boot files for the module.

        Acquires _CODEGEN_SEMAPHORE before making any LLM calls so that at
        most 4 modules generate code simultaneously — prevents Anthropic 429s.
        """
        migration_id = state["migration_id"]
        module       = state.get("module", {"module_id": "core", "module_name": "core"})
        arch_plan    = state.get("arch_plan", {})

        module_name = module.get("module_name", module.get("module_id", "core"))
        self._logger.info("CodeGenAgent.run", module=module_name)

        generated: list[dict] = []

        # ── Gradle scaffold (no LLM — runs outside semaphore) ────────────
        gradle_files = self._gradle.generate(arch_plan)
        for gf in gradle_files:
            self._ss.save_generated_file(migration_id, gf["path"], "GRADLE", gf["content"], [])
            generated.append(gf)

        # ── LLM-gated section: React + Spring (throttled) ─────────────────
        with _CODEGEN_SEMAPHORE:
            # ── React component ───────────────────────────────────────────
            react_files = self._react.generate(migration_id, module_name,
                                                self._find_bc(arch_plan, module_name), state)
            for rf in react_files:
                self._ss.save_generated_file(migration_id, rf["path"], "REACT", rf["content"], [])
                generated.append(rf)

            # ── Spring Boot module ────────────────────────────────────────
            spring_files = self._spring.generate(migration_id, module_name,
                                                  self._find_bc(arch_plan, module_name), state)
            for sf in spring_files:
                self._ss.save_generated_file(migration_id, sf["path"], "SPRING", sf["content"], [])
                generated.append(sf)

        # Return ONLY generated_files — parallel Send workers MUST NOT write
        # non-annotated keys (migration_id, current_phase, arch_plan, etc.).
        # LangGraph merges each worker's list via the operator.add reducer on
        # generated_files; returning the full state causes INVALID_CONCURRENT_GRAPH_UPDATE.
        return {"generated_files": generated}

    def call_llm(self, system: str, user: str) -> str:
        """Public method used by ReactGenerator / SpringGenerator."""
        return self._call_text(system, user)

    @staticmethod
    def _find_bc(arch_plan: dict, module_name: str) -> dict:
        for bc in arch_plan.get("bounded_contexts", []):
            if bc.get("name", "").lower() == module_name.lower():
                return bc
        return {"name": module_name, "rest_endpoints": [], "jpa_entities": [], "react_components": []}
