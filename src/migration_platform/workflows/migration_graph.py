"""
LangGraph 1.x StateGraph — complete migration workflow.

LangGraph 1.x advances used:
  - interrupt() called inside a node (replaces interrupt_before compile flag)
  - Send API for parallel module-level code generation fan-out
  - Command for conditional routing with embedded state updates
  - START constant for explicit entry-point declaration
  - langgraph.types for all new primitives
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, interrupt
from migration_platform.storage.checkpoint_store import PersistentMemorySaver

from migration_platform.agents.architecture_agent import ArchitectureAgent
from migration_platform.agents.codegen_agent import CodeGenAgent
from migration_platform.agents.graph_agent import GraphAgent
from migration_platform.agents.integration_agent import IntegrationAgent
from migration_platform.agents.parser_agent import ParserAgent
from migration_platform.agents.planner_agent import PlannerAgent
from migration_platform.agents.repo_agent import RepoAgent
from migration_platform.agents.testing_agent import TestingAgent
from migration_platform.agents.validation_agent import ValidationAgent
from migration_platform.codegen.context_builder import ContextBuilder
from migration_platform.config.settings import get_settings
from migration_platform.core.logging import get_logger
from migration_platform.graph.graph_store import GraphStore
from migration_platform.rag.embedder import Embedder
from migration_platform.rag.retriever import Retriever
from migration_platform.rag.vector_store import VectorStore
from migration_platform.storage.cache_store import CacheStore
from migration_platform.storage.state_store import StateStore
from migration_platform.workflows.state import MigrationState

logger = get_logger(__name__)


# ── Node functions ────────────────────────────────────────────────────────────

def _await_approval_node(state: MigrationState) -> dict:
    """
    LangGraph 1.x interrupt() — called INSIDE the node.

    The graph suspends here and returns the interrupt payload to the caller.
    When resumed via graph.update_state() + graph.invoke(None, config),
    interrupt() returns the value passed to update_state.

    This replaces the 0.x pattern of interrupt_before=["node_name"] at compile time.
    """
    logger.info("workflow.approval_gate_reached", migration_id=state.get("migration_id"))

    # interrupt() suspends the graph and surfaces these artifacts to the UI
    decision = interrupt({
        "migration_id":    state.get("migration_id"),
        "diagrams":        state.get("diagrams", []),
        "migration_plan":  state.get("migration_plan", {}),
        "soap_report":     state.get("soap_report", {}),
        "sequence_diagrams": state.get("sequence_diagrams", []),
        "message":         "Review the migration plan. Approve to generate code, reject to regenerate.",
    })

    # When resumed, decision = {"status": "approved"|"rejected", "comment": "..."}
    return {
        "approval_status":  decision.get("status", "pending"),
        "approval_comment": decision.get("comment", ""),
        "current_phase":    "approval_received",
    }


def _route_on_approval(state: MigrationState) -> str:
    """Conditional edge: approved → validate, rejected → redesign."""
    status = state.get("approval_status", "pending")
    logger.info("workflow.routing", approval=status)
    return "validate_plan" if status == "approved" else "design_architecture"


def _route_on_validation(state: MigrationState) -> str:
    """Block code gen if CRITICAL issues remain unresolved."""
    report = state.get("validation_report", {})
    if report.get("critical_count", 0) > 0:
        logger.warning("workflow.validation_blocked", critical=report["critical_count"])
        return END
    return "dispatch_codegen"


def _dispatch_codegen_node(state: MigrationState) -> dict:
    """
    Pass-through node — exists only so the graph has a named checkpoint
    between validation and the Send fan-out edge.
    The actual parallel routing is handled by _dispatch_codegen (edge function).
    """
    return {"current_phase": "dispatching"}


_MAX_PARALLEL_MODULES = 6   # hard cap — keeps Anthropic API within rate limits


def _dispatch_codegen(state: MigrationState) -> list[Send]:
    """
    LangGraph 1.x Send API — fan-out to parallel per-module code generation.

    Returns a list of Send objects; LangGraph executes them concurrently.
    Each Send carries the module-specific slice of state to a worker node.
    Used ONLY as a conditional-edge routing function, never as a node.

    Deduplication:  Louvain community detection often labels many distinct
    clusters with the same domain name (e.g. "blog"×9, "core"×2).
    We merge classes from same-named clusters into a single module so each
    bounded-context is generated exactly once.

    Rate-limit cap: each module worker makes 2 LLM calls (React + Spring).
    Too many parallel workers cause Anthropic 429 errors.  Cap at
    _MAX_PARALLEL_MODULES workers to keep concurrent API calls manageable.
    """
    modules      = state.get("module_clusters", [])
    migration_id = state.get("migration_id", "")
    if not migration_id:
        raise ValueError("migration_id missing from state — workflow state may be corrupted")

    if not modules:
        # Fallback: single-module generation
        return [Send("generate_module", {
            "migration_id": migration_id,
            "module": {"module_id": "core", "module_name": "core", "classes": [], "size": 0},
            "arch_plan":   state.get("arch_plan", {}),
            "soap_report": state.get("soap_report", {}),
            "jdbc_map":    state.get("jdbc_map", {}),
        })]

    # ── Deduplicate by module_name ─────────────────────────────────────────
    # Merge classes from clusters that share the same domain label so each
    # bounded-context (e.g. "blog") is generated exactly once.
    merged: dict[str, dict] = {}
    for mod in modules:
        key = (mod.get("module_name") or mod.get("module_id", "core")).lower().strip()
        if key in merged:
            # Accumulate classes from duplicate-named clusters
            existing_classes = merged[key].get("classes", [])
            new_classes      = mod.get("classes", [])
            merged[key]["classes"] = list(dict.fromkeys(existing_classes + new_classes))
            merged[key]["size"]    = len(merged[key]["classes"])
        else:
            merged[key] = dict(mod)

    unique_modules = list(merged.values())

    # ── Cap to avoid rate limits ───────────────────────────────────────────
    if len(unique_modules) > _MAX_PARALLEL_MODULES:
        logger.warning(
            "dispatch_codegen: capping modules",
            total=len(unique_modules),
            cap=_MAX_PARALLEL_MODULES,
        )
        unique_modules = unique_modules[:_MAX_PARALLEL_MODULES]

    logger.info(
        "dispatch_codegen: sending",
        unique_modules=len(unique_modules),
        raw_clusters=len(modules),
    )

    common = {
        "arch_plan":   state.get("arch_plan", {}),
        "soap_report": state.get("soap_report", {}),
        "jdbc_map":    state.get("jdbc_map", {}),
    }
    return [
        Send("generate_module", {"migration_id": migration_id, "module": mod, **common})
        for mod in unique_modules
    ]


def _aggregate_codegen(state: MigrationState) -> dict:
    """
    Write all generated files to disk after parallel module workers finish.

    LangGraph has already merged every worker's generated_files list via the
    operator.add reducer, so state["generated_files"] contains every file from
    every module.  We route them into two project trees:

        output/<migration_id>/spring-boot/<path>   ← SPRING, GRADLE, CONFIG
        output/<migration_id>/react/<path>          ← REACT

    We also scaffold the React project files (package.json, tsconfig.json,
    vite.config.ts) that `npm run build` needs but the LLM never produces.
    """
    from migration_platform.config.settings import get_settings

    migration_id    = state.get("migration_id", "unknown")
    generated_files = state.get("generated_files", [])
    settings        = get_settings()

    spring_dir = Path(settings.output_dir) / migration_id / "spring-boot"
    react_dir  = Path(settings.output_dir) / migration_id / "react"
    spring_dir.mkdir(parents=True, exist_ok=True)
    react_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for file_record in generated_files:
        ftype   = (file_record.get("type") or "SPRING").upper()
        fpath   = file_record.get("path", "").lstrip("/")
        content = file_record.get("content", "")
        if not fpath or content is None:
            continue
        base = react_dir if ftype == "REACT" else spring_dir
        dest = base / fpath
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        written += 1

    # ── React project scaffolding ─────────────────────────────────────────
    # The LLM generates .tsx/.ts files but not the toolchain config files.
    # Without these, `npm run build` fails immediately.
    _scaffold_react_project(react_dir)

    logger.info(
        "aggregate_codegen.files_written",
        migration_id=migration_id,
        files_written=written,
        spring_dir=str(spring_dir),
        react_dir=str(react_dir),
    )
    return {
        "current_phase": "generated",
        "generation_progress": 1.0,
    }


def _scaffold_react_project(react_dir: Path) -> None:
    """Write package.json / tsconfig.json / vite.config.ts if absent."""
    pkg = react_dir / "package.json"
    if not pkg.exists():
        pkg.write_text(json.dumps({
            "name": "migrated-app",
            "version": "0.1.0",
            "private": True,
            "type": "module",
            "scripts": {
                "dev":   "vite",
                "build": "tsc && vite build",
                "preview": "vite preview"
            },
            "dependencies": {
                "react":     "^18.2.0",
                "react-dom": "^18.2.0",
                "axios":     "^1.6.0"
            },
            "devDependencies": {
                "typescript":          "^5.2.0",
                "@types/react":        "^18.2.0",
                "@types/react-dom":    "^18.2.0",
                "vite":                "^5.0.0",
                "@vitejs/plugin-react":"^4.0.0"
            }
        }, indent=2), encoding="utf-8")

    tsconfig = react_dir / "tsconfig.json"
    if not tsconfig.exists():
        tsconfig.write_text(json.dumps({
            "compilerOptions": {
                "target":            "ES2020",
                "useDefineForClassFields": True,
                "lib":               ["ES2020", "DOM", "DOM.Iterable"],
                "module":            "ESNext",
                "skipLibCheck":      True,
                "moduleResolution":  "bundler",
                "allowImportingTsExtensions": True,
                "resolveJsonModule": True,
                "isolatedModules":   True,
                "noEmit":            True,
                "jsx":               "react-jsx",
                "strict":            True,
                "noUnusedLocals":    False,
                "noUnusedParameters": False
            },
            "include": ["src"]
        }, indent=2), encoding="utf-8")

    vite_cfg = react_dir / "vite.config.ts"
    if not vite_cfg.exists():
        vite_cfg.write_text(
            "import { defineConfig } from 'vite';\n"
            "import react from '@vitejs/plugin-react';\n\n"
            "export default defineConfig({\n"
            "  plugins: [react()],\n"
            "});\n",
            encoding="utf-8",
        )

    # Minimal entry point if the LLM did not generate one
    main_tsx = react_dir / "src" / "main.tsx"
    if not main_tsx.exists():
        main_tsx.parent.mkdir(parents=True, exist_ok=True)
        main_tsx.write_text(
            "import React from 'react';\n"
            "import ReactDOM from 'react-dom/client';\n\n"
            "// Auto-generated entry point — import your components here\n"
            "const App = () => <div>Migration complete</div>;\n\n"
            "ReactDOM.createRoot(document.getElementById('root')!).render(\n"
            "  <React.StrictMode><App /></React.StrictMode>\n"
            ");\n",
            encoding="utf-8",
        )

    index_html = react_dir / "index.html"
    if not index_html.exists():
        index_html.write_text(
            "<!doctype html>\n<html lang=\"en\">\n<head>\n"
            "  <meta charset=\"UTF-8\" />\n"
            "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n"
            "  <title>Migrated App</title>\n</head>\n<body>\n"
            "  <div id=\"root\"></div>\n"
            "  <script type=\"module\" src=\"/src/main.tsx\"></script>\n"
            "</body>\n</html>\n",
            encoding="utf-8",
        )


# ── Graph factory ─────────────────────────────────────────────────────────────

def build_migration_graph() -> Any:
    """
    Construct and compile the LangGraph 1.x StateGraph.

    Topology:
      START
        → ingest_repo → parse_and_embed → build_graph
        → detect_integrations → design_architecture → create_plan
        → await_approval          ← interrupt() suspends here
        → (approved) validate_plan → dispatch_codegen
                                      ↳ [Send] generate_module (parallel)
                                      ↳ aggregate_codegen
                                      → test_and_fix → END
        → (rejected) design_architecture   ← loop back
    """
    settings = get_settings()

    # ── Shared infrastructure ─────────────────────────────────────────────
    vector_store = VectorStore(persist_dir=settings.chroma_persist_dir)
    state_store  = StateStore(db_path=str(settings.duckdb_path))
    graph_store  = GraphStore(persist_path=settings.graph_persist_path)
    cache_store  = CacheStore(cache_dir=settings.cache_dir)
    embedder     = Embedder()
    retriever    = Retriever(vector_store, embedder, graph_store)
    ctx_builder  = ContextBuilder(vector_store, graph_store, embedder)

    # ── Agent instances ───────────────────────────────────────────────────
    repo_agent        = RepoAgent()
    parser_agent      = ParserAgent(vector_store, state_store, embedder)
    graph_agent       = GraphAgent(vector_store, graph_store)
    integration_agent = IntegrationAgent(graph_store, state_store)
    arch_agent        = ArchitectureAgent(vector_store, graph_store, embedder)
    planner_agent     = PlannerAgent()
    validation_agent  = ValidationAgent()
    codegen_agent     = CodeGenAgent(ctx_builder, state_store)
    testing_agent     = TestingAgent(state_store)

    # ── Build StateGraph ──────────────────────────────────────────────────
    builder = StateGraph(MigrationState)

    # Phase A nodes
    builder.add_node("ingest_repo",         repo_agent.run)
    builder.add_node("parse_and_embed",     parser_agent.run)
    builder.add_node("build_graph",         graph_agent.run)
    builder.add_node("detect_integrations", integration_agent.run)
    builder.add_node("design_architecture", arch_agent.run)
    builder.add_node("create_plan",         planner_agent.run)

    # Human gate — uses LangGraph 1.x interrupt() internally
    builder.add_node("await_approval",      _await_approval_node)

    # Phase B nodes
    builder.add_node("validate_plan",  validation_agent.run)
    builder.add_node("dispatch_codegen", _dispatch_codegen_node)
    builder.add_node("generate_module",  codegen_agent.run)    # receives Send payloads
    builder.add_node("aggregate_codegen", _aggregate_codegen)
    builder.add_node("test_and_fix",     testing_agent.run)

    # ── Phase A edges ─────────────────────────────────────────────────────
    builder.add_edge(START,                 "ingest_repo")
    builder.add_edge("ingest_repo",         "parse_and_embed")
    builder.add_edge("parse_and_embed",     "build_graph")
    builder.add_edge("build_graph",         "detect_integrations")
    builder.add_edge("detect_integrations", "design_architecture")
    builder.add_edge("design_architecture", "create_plan")
    builder.add_edge("create_plan",         "await_approval")

    # Conditional edge at approval gate
    builder.add_conditional_edges(
        "await_approval",
        _route_on_approval,
        {
            "validate_plan":      "validate_plan",
            "design_architecture": "design_architecture",
        },
    )

    # Phase B edges
    builder.add_conditional_edges(
        "validate_plan",
        _route_on_validation,
        {
            "dispatch_codegen": "dispatch_codegen",
            END: END,
        },
    )

    # Send fan-out: dispatch_codegen → [parallel] generate_module
    builder.add_conditional_edges(
        "dispatch_codegen",
        _dispatch_codegen,
        ["generate_module"],
    )
    builder.add_edge("generate_module",   "aggregate_codegen")
    builder.add_edge("aggregate_codegen", "test_and_fix")
    builder.add_edge("test_and_fix",      END)

    # ── Compile with persistent checkpointer (survives server restarts) ─────
    checkpointer = PersistentMemorySaver(persist_path=settings.checkpoint_path)
    compiled = builder.compile(checkpointer=checkpointer)

    logger.info("workflow.graph_compiled_langgraph_1x",
                nodes=list(builder.nodes.keys()) if hasattr(builder, "nodes") else "n/a")
    return compiled


# (duplicate _route_on_approval removed — canonical definition is above)
