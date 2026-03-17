"""
IntegrationAgent — Phase A / Step 4.

LangChain 1.x advances:
  - with_structured_output(SOAPReport) for type-safe SOAP inventory
  - Batched LCEL chains with RunnableLambda transformations
  - ChatPromptTemplate variable injection
"""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from migration_platform.agents.base import BaseAgent
from migration_platform.graph.graph_store import GraphStore
from migration_platform.storage.state_store import StateStore
from migration_platform.workflows.state import MigrationState

_INTEGRATION_SYSTEM = """
You are an enterprise integration analyst. Analyse the SOAP integration points below.
For each integration, determine:
- The correct migration option (A=REST adapter, B=Spring WS client, C=OpenFeign if REST available)
- Risk complexity (LOW/MEDIUM/HIGH based on operation count and coupling)
- Specific notes on how to implement the chosen option with Spring Boot + Gradle

Be thorough — missing an integration is a critical failure.
""".strip()

_BATCH_SIZE = 15


# ── Structured output schemas ─────────────────────────────────────────────────

class EnrichedIntegration(BaseModel):
    service_name:     str
    endpoint_url:     str = ""
    wsdl_url:         str = ""
    stub_class:       str = ""
    operations:       list[str] = []
    callsite_class:   str = ""
    callsite_method:  str = ""
    migration_option: Literal["A", "B", "C"] = "A"
    complexity:       Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    implementation_notes: str = ""


class SOAPReport(BaseModel):
    integrations: list[EnrichedIntegration] = []
    total:        int = 0
    high_risk:    int = 0


class IntegrationAgent(BaseAgent):
    """
    Produces a complete SOAP integration report.

    Uses with_structured_output(SOAPReport) to get a typed, validated
    list of integrations with migration recommendations.
    """

    def __init__(self, graph_store: GraphStore, state_store: StateStore) -> None:
        super().__init__()
        self._gs = graph_store
        self._ss = state_store

    def run(self, state: MigrationState) -> MigrationState:
        migration_id = state["migration_id"]
        self._logger.info("IntegrationAgent starting", migration_id=migration_id)

        raw_integrations = self._gs.get_all_soap_integrations()
        self._logger.info("Raw SOAP nodes from graph", count=len(raw_integrations))

        all_enriched: list[dict] = []

        # Process in batches — stay within token budget
        for i in range(0, max(len(raw_integrations), 1), _BATCH_SIZE):
            batch = raw_integrations[i : i + _BATCH_SIZE]
            if not batch:
                break

            user_input = (
                f"SOAP integration batch {i // _BATCH_SIZE + 1}:\n"
                f"{json.dumps(batch, indent=2)}"
            )

            # with_structured_output → typed SOAPReport per batch
            report: SOAPReport | None = self._call_structured(
                _INTEGRATION_SYSTEM, user_input, SOAPReport, model="claude"
            )

            if report:
                for item in report.integrations:
                    d = item.model_dump()
                    d["migration_id"] = migration_id
                    all_enriched.append(d)
                    self._ss.save_soap_integration(migration_id, d)

        # JDBC table map from graph edges
        jdbc_tables: list[str] = list({
            v
            for _, v, d in self._gs.G.edges(data=True)
            if d.get("rel_type") == "QUERIES"
        })

        soap_report = {
            "integrations": all_enriched,
            "total":        len(all_enriched),
            "high_risk":    sum(1 for x in all_enriched if x.get("complexity") == "HIGH"),
        }

        # Derive JPA entity class names from table names so the ValidationAgent
        # sees real mappings instead of just raw table names.
        # Convention: strip leading T_ / TBL_ / TB_ prefix, then PascalCase.
        # e.g.  T_ARTICLE_DELET → ArticleDelet,  T_USER → User
        entity_map: dict[str, str] = {}
        for table in jdbc_tables:
            clean = table
            for prefix in ("T_", "TBL_", "TB_"):
                if clean.upper().startswith(prefix):
                    clean = clean[len(prefix):]
                    break
            entity_name = "".join(part.capitalize() for part in clean.split("_") if part)
            entity_map[table] = entity_name

        state["soap_report"]             = soap_report
        state["soap_integration_count"]  = len(all_enriched)
        state["jdbc_map"]                = {"tables": jdbc_tables, "entity_map": entity_map}
        state["current_phase"]           = "detected"

        self._logger.info(
            "IntegrationAgent complete",
            soap=len(all_enriched),
            jdbc_tables=len(jdbc_tables),
        )
        return state
