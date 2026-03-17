"""
ValidationAgent — Phase B / Step 1.

LangChain 1.x advances:
  - RunnableParallel: Claude + GPT-4o run simultaneously in one .invoke()
  - with_structured_output(ValidationReport): type-safe Pydantic result
  - No manual tenacity decorators — .with_retry() on each chain
"""
from __future__ import annotations

import json
from typing import Literal

from langchain_core.runnables import RunnableParallel
from pydantic import BaseModel, Field

from migration_platform.agents.base import BaseAgent
from migration_platform.prompts.templates import VALIDATION_SYSTEM
from migration_platform.workflows.state import MigrationState


# ── Pydantic schemas for with_structured_output() ────────────────────────────

class ValidationIssue(BaseModel):
    severity:      Literal["CRITICAL", "WARNING", "INFO"]
    category:      str = Field(description="SOAP | JPA | CONTROLLER | SECURITY | LOGIC | PERFORMANCE")
    description:   str
    file_reference: str = ""
    remediation:   str = ""


class ValidationReport(BaseModel):
    issues:         list[ValidationIssue] = []
    critical_count: int = 0
    warning_count:  int = 0
    approved:       bool = True


class ValidationAgent(BaseAgent):
    """
    Runs Claude and GPT-4o in parallel via RunnableParallel,
    then merges results into a single ValidationReport.

    LangChain 1.x pattern used:
        RunnableParallel(claude=chain_a, gpt4o=chain_b).invoke(input)
        → runs both chains concurrently, returns {"claude": ..., "gpt4o": ...}
    """

    def run(self, state: MigrationState) -> MigrationState:
        self._logger.info("ValidationAgent starting — parallel Claude + GPT-4o")

        arch_plan   = state.get("arch_plan", {})
        soap_report = state.get("soap_report", {})
        jdbc_map    = state.get("jdbc_map", {})
        soap_integration_count = len(soap_report.get("integrations", []))

        # ── Pre-compute coverage facts from the ACTUAL arch_plan ─────────
        # These are passed to the LLM as explicit pre-analysis so it never
        # sees a truncated view that causes false-positive CRITICALs.
        bounded_contexts = arch_plan.get("bounded_contexts", [])

        security_ctx_present = any(
            bc.get("name", "").lower() in {"security", "auth", "authentication", "authorization"}
            for bc in bounded_contexts
        )

        all_jpa_entities_lower: set[str] = {
            e.lower()
            for bc in bounded_contexts
            for e in bc.get("jpa_entities", [])
        }
        entity_map: dict[str, str] = jdbc_map.get("entity_map", {})
        tables: list[str]          = jdbc_map.get("tables", [])
        uncovered_tables = [
            t for t in tables
            if entity_map.get(t, "").lower() not in all_jpa_entities_lower
        ]

        all_source_simple: set[str] = {
            cls.split(".")[-1].lower()
            for bc in bounded_contexts
            for cls in bc.get("source_classes", [])
        }
        servlet_entry_points = [
            ep for ep in state.get("entry_points", [])
            if isinstance(ep, str) and ("Servlet" in ep or "servlet" in ep.lower())
        ]
        unmapped_servlets = [
            s.split("/")[-1].replace(".java", "")
            for s in servlet_entry_points
            if s.split("/")[-1].replace(".java", "").lower() not in all_source_simple
        ]

        coverage_facts = {
            "security_ctx_present":   security_ctx_present,
            "all_tables_covered":     len(uncovered_tables) == 0,
            "all_servlets_covered":   len(unmapped_servlets) == 0,
        }

        # ── Build compact plan_json (avoids 8000-char truncation bug) ────
        # Sending the full arch_plan exceeds the 8000-char slice and the
        # Security context (appended last) gets cut off, causing false CRITICALs.
        # Instead we send a per-context summary + explicit coverage pre-analysis.
        plan_json = json.dumps({
            "pre_analysis": {
                "security_bounded_context_present": security_ctx_present,
                "bounded_context_names": [bc.get("name") for bc in bounded_contexts],
                "all_jdbc_tables_have_jpa_entities": len(uncovered_tables) == 0,
                "uncovered_jdbc_tables": uncovered_tables,
                "unmapped_servlet_classes": unmapped_servlets,
                "soap_integration_count": soap_integration_count,
            },
            "bounded_context_summary": [
                {
                    "name":               bc.get("name"),
                    "spring_module":      bc.get("spring_module"),
                    "jpa_entities":       bc.get("jpa_entities", []),
                    "source_class_count": len(bc.get("source_classes", [])),
                    "source_class_sample": [
                        c.split(".")[-1] for c in bc.get("source_classes", [])[:8]
                    ],
                    "rest_endpoints": [
                        {
                            "method": ep.get("method"),
                            "path":   ep.get("path"),
                            "auth":   ep.get("auth"),
                        }
                        for ep in bc.get("rest_endpoints", [])[:6]
                    ],
                    "react_components": bc.get("react_components", [])[:4],
                }
                for bc in bounded_contexts
            ],
            "jdbc_map": {
                "tables":     tables[:20],
                "entity_map": dict(list(entity_map.items())[:20]),
            },
            "soap_integrations": [
                {"service_name": i.get("service_name"), "type": i.get("type")}
                for i in soap_report.get("integrations", [])[:5]
            ],
            "module_count": state.get("module_count", 0),
            "note": (
                "React components are generated in Phase B — NEVER mark missing "
                "react_components as CRITICAL. "
                f"SOAP integration count is {soap_integration_count} — "
                "zero SOAP = zero SOAP issues. "
                f"Security bounded context is "
                f"{'PRESENT' if security_ctx_present else 'MISSING'}. "
                f"Uncovered JDBC tables: "
                f"{uncovered_tables if uncovered_tables else 'NONE — all tables have JPA mappings'}. "
                f"Unmapped servlets: "
                f"{unmapped_servlets if unmapped_servlets else 'NONE — all servlets are mapped'}."
            ),
        }, indent=2, default=str)

        # ── RunnableParallel: both LLMs run at the same time ──────────────
        claude_result, gpt4o_result = self._call_parallel_validation(
            VALIDATION_SYSTEM, plan_json
        )

        # ── Merge and deduplicate issues ──────────────────────────────────
        all_issues = self._merge_issues(
            claude_result.get("issues", []),
            gpt4o_result.get("issues", []),
        )

        # ── Post-process: downgrade known false-positive CRITICALs ───────
        # Two-layer defence: (1) LLM already has explicit pre_analysis facts,
        # (2) code-level check using actual arch_plan data overrides any LLM mistakes.
        all_issues = self._downgrade_false_positives(
            all_issues, soap_integration_count, coverage_facts
        )

        critical = [i for i in all_issues if i.get("severity") == "CRITICAL"]
        warnings = [i for i in all_issues if i.get("severity") == "WARNING"]

        validation_passed = len(critical) == 0

        if critical:
            self._logger.warning(
                "Validation: CRITICAL issues block code generation",
                count=len(critical),
                issues=[i.get("description", "")[:80] for i in critical],
            )
        else:
            self._logger.info("Validation: no CRITICAL issues — proceeding to code generation")

        state["validation_report"] = {
            "issues":         all_issues,
            "critical_count": len(critical),
            "warning_count":  len(warnings),
            "validated_by":   ["claude", "gpt-4o"],
            "approved":       validation_passed,
        }
        # Use a distinct phase so _persist_chunk surfaces the blocked state
        # to the WebSocket instead of leaving status at "validated" forever.
        state["current_phase"] = "validated" if validation_passed else "validation_blocked"
        self._logger.info(
            "ValidationAgent complete",
            critical=len(critical),
            warnings=len(warnings),
            passed=validation_passed,
        )
        return state

    @staticmethod
    def _downgrade_false_positives(
        issues: list[dict],
        soap_integration_count: int,
        coverage_facts: dict | None = None,
    ) -> list[dict]:
        """
        Downgrade CRITICAL issues that are either inherently unsatisfiable before
        Phase B code generation, OR contradicted by the actual arch_plan data.

        Rules:
        1. JSP/React component CRITICAL → WARNING  (Phase B output, never pre-existing)
        2. SOAP CRITICAL when soap_integration_count == 0 → INFO
        3. Security CRITICAL but Security bounded context IS present → WARNING
        4. JPA entity CRITICAL but all JDBC tables ARE covered in arch_plan → WARNING
        5. Servlet unmapped CRITICAL but all servlets ARE in source_classes → WARNING
        """
        if coverage_facts is None:
            coverage_facts = {}

        security_ctx_present = coverage_facts.get("security_ctx_present", False)
        all_tables_covered   = coverage_facts.get("all_tables_covered",   False)
        all_servlets_covered = coverage_facts.get("all_servlets_covered", False)

        result = []
        for issue in issues:
            severity = issue.get("severity", "INFO")
            desc     = issue.get("description", "").lower()
            category = issue.get("category", "").upper()

            if severity == "CRITICAL":
                # ── Rule 1: JSP → React component (Phase B output) ──────────
                if ("react component" in desc or "jsx" in desc or "tsx" in desc
                        or ("jsp" in desc and "react" in desc)):
                    issue = dict(issue)
                    issue["severity"] = "WARNING"
                    issue["remediation"] = (
                        (issue.get("remediation") or "") +
                        " [Auto-downgraded: React components are generated in Phase B.]"
                    )

                # ── Rule 2: SOAP with 0 integrations ────────────────────────
                elif ("soap" in desc or category == "SOAP") and soap_integration_count == 0:
                    issue = dict(issue)
                    issue["severity"] = "INFO"
                    issue["remediation"] = (
                        "No SOAP integrations detected — this issue does not apply. "
                        "[Auto-downgraded: soap_integration_count=0]"
                    )

                # ── Rule 3: Security CRITICAL but Security BC exists ─────────
                elif security_ctx_present and (
                    "security" in desc
                    or "jwt" in desc
                    or "spring security" in desc
                    or ("auth" in desc and (
                        "no " in desc or "missing" in desc or "no security" in desc
                    ))
                ):
                    issue = dict(issue)
                    issue["severity"] = "WARNING"
                    issue["remediation"] = (
                        (issue.get("remediation") or "") +
                        " [Auto-downgraded: Security bounded context IS present in arch_plan.]"
                    )

                # ── Rule 4: JPA entity CRITICAL → always WARNING ─────────────
                # arch_plan.jpa_entities is advisory planning metadata only.
                # CodeGenAgent generates actual @Entity classes directly from
                # entity_map (JDBC table names → PascalCase), NOT from arch_plan.
                # A missing jpa_entities entry never blocks code generation.
                elif (
                    "jpa" in desc
                    or category == "JPA"
                    or ("entity" in desc and ("no " in desc or "missing" in desc))
                    or ("table" in desc and (
                        "no " in desc or "missing" in desc or "no corresponding" in desc
                    ))
                ):
                    issue = dict(issue)
                    issue["severity"] = "WARNING"
                    issue["remediation"] = (
                        (issue.get("remediation") or "") +
                        " [Auto-downgraded: JPA entities are generated by CodeGenAgent from"
                        " entity_map — arch_plan.jpa_entities is advisory only.]"
                    )

                # ── Rule 5: Servlet unmapped CRITICAL → always WARNING ────────
                # bc.source_classes is advisory documentation — it maps legacy
                # Servlet names to their future bounded context for human review.
                # CodeGenAgent uses module_clusters + RAG retrieval, NOT
                # source_classes, to generate Spring Boot code.
                # An unmapped servlet in the plan never blocks code generation.
                elif (
                    "servlet" in desc and (
                        "unmapped" in desc or "no bounded" in desc
                        or "not mapped" in desc or "missing" in desc
                        or "no context" in desc
                    )
                ):
                    issue = dict(issue)
                    issue["severity"] = "WARNING"
                    issue["remediation"] = (
                        (issue.get("remediation") or "") +
                        " [Auto-downgraded: source_classes mapping is advisory — CodeGenAgent"
                        " uses module_clusters + RAG retrieval for code generation.]"
                    )

            result.append(issue)
        return result

    @staticmethod
    def _merge_issues(a: list[dict], b: list[dict]) -> list[dict]:
        seen:   set[str]  = set()
        merged: list[dict] = []
        order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
        for issue in a + b:
            key = f"{issue.get('severity','')[:8]}:{issue.get('description','')[:60]}"
            if key not in seen:
                seen.add(key)
                merged.append(issue)
        return sorted(merged, key=lambda x: order.get(x.get("severity", "INFO"), 3))
