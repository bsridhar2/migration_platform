"""
ArchitectureAgent — Phase A / Step 5.

LangChain 1.x advances:
  - with_structured_output(ArchitecturePlan): guaranteed Pydantic object back
  - ChatPromptTemplate.from_messages() with typed variable injection
  - LCEL chain composition: prompt | model.with_structured_output(schema)
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from migration_platform.agents.base import BaseAgent
from migration_platform.codegen.context_builder import ContextBuilder
from migration_platform.graph.graph_store import GraphStore
from migration_platform.prompts.templates import ARCHITECTURE_SYSTEM
from migration_platform.rag.embedder import Embedder
from migration_platform.rag.retriever import Retriever
from migration_platform.rag.vector_store import VectorStore
from migration_platform.workflows.state import MigrationState


# ── Structured output schemas (LangChain 1.x with_structured_output) ─────────

class RestEndpoint(BaseModel):
    method:   str = Field(description="HTTP verb: GET | POST | PUT | DELETE | PATCH")
    path:     str = Field(description="REST path e.g. /api/v1/orders/{id}")
    response: str = Field(description="Brief response description")
    auth:     bool = Field(default=True)


class BoundedContext(BaseModel):
    name:            str
    description:     str
    source_classes:  list[str] = []
    spring_module:   str = ""
    rest_endpoints:  list[RestEndpoint] = []
    jpa_entities:    list[str] = []
    react_components: list[str] = []


class SoapMigrationEntry(BaseModel):
    service_name:  str
    chosen_option: str = Field(description="A=REST adapter | B=Spring WS | C=OpenFeign")
    notes:         str = ""


class ArchitecturePlan(BaseModel):
    bounded_contexts: list[BoundedContext] = []
    soap_migration_map: list[SoapMigrationEntry] = []


class ArchitectureAgent(BaseAgent):
    """
    Designs the target React + Spring Boot architecture using RAG context.

    Uses with_structured_output(ArchitecturePlan) so the LLM response is
    automatically validated as a Pydantic object — no brittle JSON parsing.
    """

    def __init__(
        self,
        vector_store: VectorStore,
        graph_store: GraphStore,
        embedder: Embedder,
    ) -> None:
        super().__init__()
        self._retriever = Retriever(vector_store, embedder, graph_store)
        self._gs = graph_store

    def run(self, state: MigrationState) -> MigrationState:
        migration_id = state["migration_id"]
        self._logger.info("ArchitectureAgent starting", migration_id=migration_id)

        # ── 1. Retrieve representative chunks per module via RAG ──────────
        modules    = state.get("module_clusters", [])
        jdbc_map   = state.get("jdbc_map", {})
        entity_map: dict[str, str] = jdbc_map.get("entity_map", {})

        module_summaries: list[dict] = []
        for mod in modules[:15]:
            module_id = mod.get("module_id", "")
            classes   = mod.get("classes", [])
            chunks = self._retriever.retrieve(
                query=f"business logic service controller {module_id}",
                migration_id=migration_id,
                module_hint=module_id,
                top_k=4,
            )
            module_summaries.append({
                "module":      module_id,
                "module_name": mod.get("module_name", module_id),
                # Include the actual class names so the LLM knows what code exists
                "classes":     classes,
                "class_count": mod.get("size", 0),
                "sample_code": "\n---\n".join(c["raw_text"][:500] for c in chunks[:2]),
            })

        soap_report  = state.get("soap_report", {})
        entry_points = state.get("entry_points", [])

        # Collect ALL class names across ALL modules (not just sample code)
        all_classes_flat: list[str] = []
        for mod in modules:
            all_classes_flat.extend(mod.get("classes", []))
        # Simple names for readability
        all_simple_names = sorted({c.split(".")[-1] for c in all_classes_flat if c})

        user_input = (
            "Design the target bounded-context architecture for this migration.\n\n"
            "=== ALL SOURCE JAVA CLASS NAMES ===\n"
            f"{json.dumps(all_simple_names, indent=2)[:3000]}\n\n"
            "=== SOURCE JAVA CLASSES (grouped by module, with sample code) ===\n"
            f"{json.dumps(module_summaries, indent=2)[:4000]}\n\n"
            "=== JDBC TABLES → JPA ENTITY CLASS MAPPINGS ===\n"
            f"{json.dumps(entity_map, indent=2)}\n\n"
            "=== SOAP INTEGRATIONS ===\n"
            f"{json.dumps(soap_report.get('integrations', []), indent=2)[:1000]}\n\n"
            "=== ENTRY POINTS (servlets, JSP files) ===\n"
            f"{json.dumps(entry_points[:20], indent=2)}\n\n"
            "REQUIREMENTS:\n"
            "1. Every class name listed above MUST appear in exactly one bounded context.\n"
            "2. Every table in the JDBC entity map MUST appear in exactly one bounded context.\n"
            "3. ALWAYS include a 'Security' bounded context with JWT auth endpoints.\n"
            "4. Servlet classes (names ending in Servlet) MUST be in source_classes of their domain context.\n"
            "5. DAO classes (names ending in DaoImpl) MUST be in source_classes of their domain context.\n"
            "6. Do NOT leave bounded_contexts empty."
        )

        # ── 2. with_structured_output — Pydantic-typed response ──────────
        plan: ArchitecturePlan | None = self._call_structured(
            ARCHITECTURE_SYSTEM, user_input, ArchitecturePlan, model="claude"
        )

        if plan is None:
            self._logger.warning("ArchitectureAgent: structured output failed, using fallback")
            plan = ArchitecturePlan(bounded_contexts=[], soap_migration_map=[])

        # ── Post-process: ensure Security context always exists ───────────────
        # Even when the LLM returns a valid plan, it sometimes omits the Security context.
        security_names = {"security", "auth", "authentication", "authorization"}
        has_security = any(bc.name.lower() in security_names for bc in plan.bounded_contexts)
        if not has_security:
            # Collect security-related classes from existing contexts to move into Security
            security_keywords = {"filter", "auth", "login", "logout", "session", "security", "jwt", "token"}
            security_classes: list[str] = []
            for bc in plan.bounded_contexts:
                kept: list[str] = []
                for cls in bc.source_classes:
                    simple = cls.split(".")[-1].lower()
                    if any(kw in simple for kw in security_keywords):
                        security_classes.append(cls)
                    else:
                        kept.append(cls)
                bc.source_classes = kept

            plan.bounded_contexts.append(BoundedContext(
                name="Security",
                description="Authentication, authorization, JWT token management, Spring Security configuration",
                source_classes=security_classes,
                spring_module="security",
                jpa_entities=[],
                react_components=["LoginPage", "RegisterPage", "ProfilePage"],
                rest_endpoints=[
                    RestEndpoint(method="POST", path="/api/v1/auth/login",    response="JWT token", auth=False),
                    RestEndpoint(method="POST", path="/api/v1/auth/logout",   response="204 No Content", auth=True),
                    RestEndpoint(method="POST", path="/api/v1/auth/register", response="Created user", auth=False),
                    RestEndpoint(method="GET",  path="/api/v1/auth/me",       response="Current user profile", auth=True),
                ],
            ))
            self._logger.info("ArchitectureAgent: injected Security bounded context")

        # ── Post-process: ensure every entity_map entry is covered ───────────
        # Find any entities not yet assigned to any bounded context and assign them.
        if entity_map:
            assigned: set[str] = set()
            for bc in plan.bounded_contexts:
                assigned.update(bc.jpa_entities)
            unassigned = [e for e in entity_map.values() if e not in assigned]
            for entity in unassigned:
                # Find the best-matching bounded context by name similarity
                entity_lower = entity.lower()
                best_bc: BoundedContext | None = None
                for bc in plan.bounded_contexts:
                    if bc.name.lower() == "security":
                        continue
                    if entity_lower.startswith(bc.name.lower()) or bc.name.lower() in entity_lower:
                        best_bc = bc
                        break
                if best_bc is None:
                    # Fall back to the first non-security context
                    for bc in plan.bounded_contexts:
                        if bc.name.lower() != "security":
                            best_bc = bc
                            break
                if best_bc:
                    best_bc.jpa_entities.append(entity)
                    self._logger.info(
                        "ArchitectureAgent: assigned unmatched entity",
                        entity=entity, context=best_bc.name,
                    )

        # ── Post-process: ensure every Servlet/DAO class is in some context ──
        all_classes_all: list[str] = []
        for mod in modules:
            all_classes_all.extend(mod.get("classes", []))

        # Normalise to simple (unqualified) names for the "already assigned" check.
        # module_clusters.classes may contain FQNs (com.example.LoginServlet) while
        # bc.source_classes from the LLM uses simple names (LoginServlet).
        # Comparing FQNs against simple names makes every class look "unassigned"
        # and the overflow logic then adds duplicate entries.
        all_assigned_simple: set[str] = set()
        for bc in plan.bounded_contexts:
            for cls in bc.source_classes:
                all_assigned_simple.add(cls.split(".")[-1].lower())

        unassigned_classes = [
            c for c in all_classes_all
            if c.split(".")[-1].lower() not in all_assigned_simple
        ]
        if unassigned_classes:
            # Group by domain keyword matches; leftover goes to first non-security context
            from collections import defaultdict
            domain_overflow: dict[str, list[str]] = defaultdict(list)
            for cls in unassigned_classes:
                simple = cls.split(".")[-1].lower()
                placed = False
                for bc in plan.bounded_contexts:
                    if bc.name.lower() == "security":
                        continue
                    if bc.name.lower() in simple:
                        domain_overflow[bc.name].append(cls)
                        placed = True
                        break
                if not placed:
                    # Security-related unassigned class?
                    security_kws = {"filter", "auth", "login", "logout", "session", "security", "jwt"}
                    if any(kw in simple for kw in security_kws):
                        domain_overflow["Security"].append(cls)
                    else:
                        domain_overflow["__default__"].append(cls)

            for bc in plan.bounded_contexts:
                overflow = domain_overflow.get(bc.name, [])
                if overflow:
                    bc.source_classes = list(dict.fromkeys(bc.source_classes + overflow))

            # Default overflow → first non-security context
            default_overflow = domain_overflow.get("__default__", [])
            if default_overflow:
                for bc in plan.bounded_contexts:
                    if bc.name.lower() != "security":
                        bc.source_classes = list(dict.fromkeys(bc.source_classes + default_overflow))
                        break

        # ── Fallback: derive bounded_contexts from class names + entity_map ──
        # Used when with_structured_output returns an empty plan (no LLM contexts at all),
        # OR when the only context is Security (injected above) and there are no domain
        # contexts to hold JPA entities and source classes.
        non_security_contexts = [
            bc for bc in plan.bounded_contexts
            if bc.name.lower() not in {"security", "auth", "authentication"}
        ]
        if not non_security_contexts and (modules or entity_map):
            self._logger.warning(
                "ArchitectureAgent: empty bounded_contexts from LLM — deriving from "
                "class names and entity map"
            )
            from collections import defaultdict

            all_entities = list(entity_map.values())   # e.g. ["Article", "User", ...]

            # --- collect every fully-qualified class name across all modules ---
            all_classes: list[str] = []
            for mod in modules:
                all_classes.extend(mod.get("classes", []))

            # --- group JPA entities by domain: entity name as the domain key ---
            assigned_entities: set[str] = set()
            domain_to_entities: dict[str, list[str]] = defaultdict(list)
            domain_to_classes:  dict[str, list[str]] = defaultdict(list)

            for entity in all_entities:
                entity_lower = entity.lower()
                # Skip if entity matches security keywords — goes to Security context
                if entity_lower in {"user"} or any(kw in entity_lower for kw in {"auth", "token", "session"}):
                    domain_to_entities[entity].append(entity)
                    matched = [c for c in all_classes if entity_lower in c.lower()]
                    domain_to_classes[entity].extend(matched)
                    assigned_entities.add(entity)
                    continue
                matched = [c for c in all_classes if entity_lower in c.lower()]
                domain_to_entities[entity].append(entity)
                domain_to_classes[entity].extend(matched)
                assigned_entities.add(entity)

            # Leftover entities with no matching class → place in first domain or "Core"
            unmatched_ents = [e for e in all_entities if e not in assigned_entities]
            if unmatched_ents:
                if domain_to_entities:
                    first_domain = next(iter(domain_to_entities))
                    domain_to_entities[first_domain].extend(unmatched_ents)
                else:
                    domain_to_entities["Core"].extend(unmatched_ents)
                    domain_to_classes["Core"].extend(all_classes)

            # If no entity map and no domains yet, fall back to one context per module_name
            if not domain_to_entities:
                grouped_fb: dict[str, list[str]] = defaultdict(list)
                for mod in modules:
                    key = mod.get("module_name") or mod.get("module_id", "core")
                    grouped_fb[key].extend(mod.get("classes", []))
                for mn, cls in grouped_fb.items():
                    domain_to_entities[mn] = []
                    domain_to_classes[mn]  = cls

            for domain, entities in domain_to_entities.items():
                domain_lower = domain.lower()
                domain_classes = list(dict.fromkeys(domain_to_classes[domain]))  # dedupe
                plan.bounded_contexts.append(BoundedContext(
                    name=domain,
                    description=f"Manages {domain} data and business logic",
                    source_classes=domain_classes[:20],
                    spring_module=domain_lower,
                    jpa_entities=entities,
                    react_components=[
                        f"{domain}ListPage",
                        f"{domain}DetailPage",
                        f"{domain}FormPage",
                    ],
                    rest_endpoints=[
                        RestEndpoint(method="GET",    path=f"/api/v1/{domain_lower}s",       response=f"List of {domain}", auth=True),
                        RestEndpoint(method="GET",    path=f"/api/v1/{domain_lower}s/{{id}}", response=f"{domain} detail",  auth=True),
                        RestEndpoint(method="POST",   path=f"/api/v1/{domain_lower}s",       response=f"Created {domain}", auth=True),
                        RestEndpoint(method="PUT",    path=f"/api/v1/{domain_lower}s/{{id}}", response=f"Updated {domain}", auth=True),
                        RestEndpoint(method="DELETE", path=f"/api/v1/{domain_lower}s/{{id}}", response="204 No Content",    auth=True),
                    ],
                ))
            # Add Security context in fallback too
            plan.bounded_contexts.append(BoundedContext(
                name="Security",
                description="Authentication, authorization, JWT token management",
                source_classes=[c for c in all_classes if any(
                    kw in c.lower() for kw in {"filter", "auth", "login", "security", "jwt"}
                )],
                spring_module="security",
                jpa_entities=[],
                react_components=["LoginPage", "RegisterPage"],
                rest_endpoints=[
                    RestEndpoint(method="POST", path="/api/v1/auth/login",    response="JWT token", auth=False),
                    RestEndpoint(method="POST", path="/api/v1/auth/logout",   response="204", auth=True),
                    RestEndpoint(method="POST", path="/api/v1/auth/register", response="Created", auth=False),
                    RestEndpoint(method="GET",  path="/api/v1/auth/me",       response="Profile", auth=True),
                ],
            ))

        # ── Fallback: derive soap_migration_map from soap_report ──────────
        if not plan.soap_migration_map:
            for si in soap_report.get("integrations", []):
                svc = si.get("service_name", "")
                if svc:
                    plan.soap_migration_map.append(SoapMigrationEntry(
                        service_name=svc,
                        chosen_option="A",
                        notes="Auto-assigned REST adapter (fallback)",
                    ))

        # ── 3. Generate Mermaid diagrams ──────────────────────────────────
        diagrams = self._build_diagrams(plan, soap_report, state)

        arch_plan_dict = plan.model_dump()

        state["arch_plan"]    = arch_plan_dict
        state["diagrams"]     = diagrams
        # module_count reflects actual parsed clusters, not just LLM-returned contexts
        state["module_count"] = len(modules) if modules else len(plan.bounded_contexts)
        state["current_phase"] = "designed"

        self._logger.info(
            "ArchitectureAgent complete",
            contexts=len(plan.bounded_contexts),
            soap_mapped=len(plan.soap_migration_map),
            diagrams=len(diagrams),
        )
        return state

    def _build_diagrams(
        self,
        plan: ArchitecturePlan,
        soap_report: dict,
        state: "MigrationState",
    ) -> list[dict]:
        soap_integrations = soap_report.get("integrations", [])
        diagrams = []

        # 1. Legacy Architecture — built DETERMINISTICALLY from parsed state data (no LLM)
        legacy_mermaid = self._build_legacy_arch_mermaid(state, soap_integrations)
        diagrams.append({
            "diagram_type":   "legacy_architecture",
            "title":          "Legacy Architecture (JSP/Servlet)",
            "mermaid_source": legacy_mermaid,
            "module":         None,
        })

        # 2. New Modern Architecture — enriched with actual REST paths and entities
        modern_mermaid = self._build_modern_arch_mermaid(plan.bounded_contexts, soap_integrations)
        diagrams.append({
            "diagram_type":   "system_architecture",
            "title":          "New Modern Architecture (Spring Boot + React)",
            "mermaid_source": modern_mermaid,
            "module":         None,
        })

        return diagrams

    @staticmethod
    def _build_legacy_arch_mermaid(state: "MigrationState", soaps: list[dict]) -> str:
        """
        Build a Mermaid diagram of the LEGACY system entirely from parsed data.
        No LLM — 100% deterministic from module_clusters, entry_points, jdbc_map.
        """
        modules      = state.get("module_clusters", [])
        entry_points = state.get("entry_points", [])
        jdbc_map     = state.get("jdbc_map", {})
        tables       = jdbc_map.get("tables", [])

        lines = ["graph TB"]

        # Client layer
        lines.append("  Browser[Browser / Client]:::client")

        # Entry points grouped by type
        servlets = [e for e in entry_points if "Servlet" in e or "servlet" in e]
        jsps     = [e for e in entry_points if e.endswith(".jsp")]
        xmls     = [e for e in entry_points if "web.xml" in e]

        if xmls:
            lines.append("  WebXML[web.xml — Deployment Descriptor]:::config")
            lines.append("  Browser --> WebXML")

        if servlets:
            lines.append("  subgraph Servlets[Servlet Layer]")
            for s in servlets[:8]:
                name = s.split("/")[-1].replace(".java", "").replace(".", "_")
                lines.append(f"    {name}[{s.split('/')[-1]}]")
            lines.append("  end")
            if xmls:
                lines.append("  WebXML --> Servlets")
            else:
                lines.append("  Browser --> Servlets")

        if jsps:
            lines.append("  subgraph JSPs[JSP View Layer]")
            for j in jsps[:8]:
                name = j.split("/")[-1].replace(".jsp", "").replace("-", "_").replace(".", "_")
                lines.append(f"    {name}[{j.split('/')[-1]}]")
            lines.append("  end")
            lines.append("  Servlets --> JSPs")

        # Business modules
        if modules:
            lines.append("  subgraph BusinessLogic[Business Logic — Java Classes]")
            for mod in modules[:6]:
                mn   = (mod.get("module_name") or mod.get("module_id", "core")).replace(" ", "_")
                size = mod.get("size", 0)
                lines.append(f"    {mn}_mod[{mn}\\n{size} classes]")
            lines.append("  end")
            if servlets:
                lines.append("  Servlets --> BusinessLogic")

        # Data layer
        if tables:
            lines.append("  subgraph DataLayer[Data Layer — JDBC / MySQL]")
            for t in tables[:8]:
                tname = t.replace(" ", "_")
                lines.append(f"    {tname}[(Table: {t})]")
            lines.append("  end")
            if modules:
                lines.append("  BusinessLogic --> DataLayer")
            elif servlets:
                lines.append("  Servlets --> DataLayer")

        # External SOAP services
        for soap in soaps[:4]:
            svc = soap.get("service_name", "SOAP").replace(":", "_").replace(" ", "_")
            ep  = soap.get("endpoint_url", "")
            label = f"{svc}\\nSOAP" if not ep else f"{svc}\\n{ep[:30]}"
            lines.append(f"  {svc}[{label}]:::soap")
            if modules:
                lines.append(f"  BusinessLogic --> {svc}")

        lines.append("  classDef client fill:#2d6a9f,stroke:#1a4971,color:#fff")
        lines.append("  classDef config fill:#6a4c93,stroke:#4a3473,color:#fff")
        lines.append("  classDef soap fill:#f9dbc8,stroke:#cc6600")
        return "\n".join(lines)

    @staticmethod
    def _build_modern_arch_mermaid(
        contexts: list[BoundedContext], soaps: list[dict]
    ) -> str:
        """
        Build the new modern architecture diagram from the actual bounded contexts.
        Shows: React pages → REST endpoints → Spring services → JPA entities → DB.
        """
        lines = ["graph TB"]

        # React frontend layer - use actual react_components
        lines.append("  subgraph Frontend[React 18 Frontend — TypeScript]")
        for bc in contexts:
            if bc.name.lower() == "security":
                continue
            for comp in bc.react_components[:2]:
                cname = comp.replace(" ", "_")
                lines.append(f"    {cname}[{comp}]")
        lines.append("    LoginPage[LoginPage]")
        lines.append("  end")

        # Spring Boot backend grouped by bounded context
        lines.append("  subgraph Backend[Spring Boot 3.3 — Gradle — Java 21]")
        for bc in contexts:
            n = bc.name.replace(" ", "_")
            mod = bc.spring_module or bc.name.lower()
            # Show the primary REST path for this context
            primary_path = ""
            if bc.rest_endpoints:
                primary_path = bc.rest_endpoints[0].path
            label = f"{bc.name}Controller\\n{primary_path}" if primary_path else f"{bc.name}Controller"
            lines.append(f"    {n}Ctrl[\"{label}\"]")
            lines.append(f"    {n}Svc[{bc.name}Service]")
        lines.append("  end")

        # JPA / Data layer - use actual entity names
        all_entities: list[str] = []
        for bc in contexts:
            all_entities.extend(bc.jpa_entities)
        lines.append("  subgraph DataLayer[Data Layer — JPA / PostgreSQL]")
        for ent in all_entities[:8]:
            lines.append(f"    {ent}Repo[{ent}Repository]")
            lines.append(f"    {ent}Tbl[({ent} table)]")
        if not all_entities:
            lines.append("    DB[(PostgreSQL)]")
        lines.append("  end")

        # Security layer
        lines.append("  subgraph Security[Spring Security + JWT]")
        lines.append("    JwtFilter[JwtAuthFilter]")
        lines.append("    SecurityConfig[SecurityConfig]")
        lines.append("  end")

        # Connections
        lines.append("  Frontend --> Backend")
        lines.append("  Backend --> DataLayer")
        lines.append("  Backend --> Security")
        for ent in all_entities[:4]:
            lines.append(f"  {ent}Ctrl --> {ent}Svc")
            lines.append(f"  {ent}Svc --> {ent}Repo")
            lines.append(f"  {ent}Repo --> {ent}Tbl")

        # External SOAP services (migrated)
        for soap in soaps[:3]:
            svc = soap.get("service_name", "SOAP").replace(":", "_").replace(" ", "_")
            lines.append(f"  {svc}Adapter[{svc}\\nREST Adapter]:::soap")
            lines.append(f"  Backend --> {svc}Adapter")

        lines.append("  classDef soap fill:#f9dbc8,stroke:#cc6600")
        return "\n".join(lines)
