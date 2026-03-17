"""Generates React TypeScript components per module."""
from __future__ import annotations
from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    from migration_platform.agents.codegen_agent import CodeGenAgent


class ReactGenerator:
    def __init__(self, agent: "CodeGenAgent") -> None:
        self._agent = agent

    def generate(self, migration_id: str, module_name: str, bc: dict[str, Any], state: dict) -> list[dict[str, str]]:
        context = self._agent._ctx.build_react_context(migration_id, module_name, bc, state.get("arch_plan", {}))
        raw = self._agent.call_llm("React 18 TypeScript developer. Output .tsx content only.", context)
        safe = module_name.replace(" ", "").replace("-", "").capitalize()
        return [
            {"path": f"src/components/{safe}/{safe}Page.tsx", "type": "REACT", "content": raw, "source_chunks": []},
            {"path": f"src/services/{safe.lower()}Service.ts", "type": "REACT",
             "content": self._service(safe, bc), "source_chunks": []},
        ]

    @staticmethod
    def _service(name: str, bc: dict) -> str:
        lines = [
            "import axios from 'axios';",
            f"const api = axios.create({{ baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8080' }});",
            "",
        ]
        for ep in bc.get("rest_endpoints", [])[:6]:
            method = ep.get("method", "GET").lower()
            path = ep.get("path", "/api/resource")
            fn = path.replace("/api/", "").replace("/", "_").replace("{", "").replace("}", "")
            lines.append(f"export const {fn} = (params?: unknown) => api.{method}('{path}', params);")
        return "\n".join(lines) + "\n"
