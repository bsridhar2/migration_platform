"""Generates Spring Boot Java classes per module."""
from __future__ import annotations
import json
from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    from migration_platform.agents.codegen_agent import CodeGenAgent


class SpringGenerator:
    def __init__(self, agent: "CodeGenAgent") -> None:
        self._agent = agent

    def generate(self, migration_id: str, module_name: str, bc: dict[str, Any], state: dict) -> list[dict[str, str]]:
        context = self._agent._ctx.build_spring_context(migration_id, module_name, bc, state)
        raw = self._agent.call_llm("Spring Boot 3.3 Java 21 developer. Output JSON array of files.", context)
        try:
            generated = json.loads(raw)
            if isinstance(generated, list):
                return [
                    {"path": f["path"], "type": "SPRING", "content": f["content"], "source_chunks": []}
                    for f in generated if "path" in f and "content" in f
                ]
        except (json.JSONDecodeError, TypeError):
            pass
        safe = module_name.replace(" ", "").capitalize()
        return [{"path": f"src/main/java/com/app/{safe.lower()}/{safe}Controller.java", "type": "SPRING", "content": raw, "source_chunks": []}]
