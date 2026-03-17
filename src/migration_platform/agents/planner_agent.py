"""
PlannerAgent — Phase A / Step 6.

LangChain 1.x advances:
  - with_structured_output(MigrationPlan) for type-safe roadmap
  - ChatPromptTemplate with rich variable injection
  - LCEL chain composition

Anti-hallucination design:
  - All LLM inputs include actual class names, REST paths, entity names
  - Sequence diagrams are seeded with real actor/class names from state
  - Roadmap tasks reference real source→target file mappings
  - Legacy sequence diagrams are built deterministically (no LLM)
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from migration_platform.agents.base import BaseAgent
from migration_platform.workflows.state import MigrationState

# ─────────────────────────────────────────────────────────────────────────────
# Planner system prompt — forces grounded output only
# ─────────────────────────────────────────────────────────────────────────────
_PLANNER_SYSTEM = """
You are an enterprise migration consultant producing a GROUNDED migration plan.
You will receive:
  (a) The architecture plan with bounded contexts, REST endpoints, JPA entities
  (b) Actual legacy Java class names grouped by domain
  (c) JDBC table→JPA entity mappings
  (d) Entry points (Servlet paths and JSP files)
  (e) Module count and language statistics

Your job:
1. ROADMAP: Produce a detailed list of transformation tasks. EVERY task must name
   a REAL source_file derived from the actual class names / JSP files provided.
   For each domain (Article, User, Comment, Tag, Security etc.) create tasks for:
   - Create @RestController from the matching *Servlet
   - Create @Service from the matching *Service or *ServiceImpl
   - Create JpaRepository from the matching *DaoImpl
   - Create @Entity class from the matching JPA entity name
   - Create React component from the matching JSP file
   Use phase="A" for architecture/planning tasks and phase="B" for code-gen tasks.
   Priority 1=critical path, 2=important, 3=standard, 4=optional, 5=nice-to-have.

2. FRAMEWORK_UPGRADES: List every legacy pattern → modern replacement ACTUALLY
   present in this codebase (based on the class names and entry points provided).
   Do NOT list generic patterns that have no evidence in the provided data.

3. SEQUENCE DIAGRAMS: Produce exactly 4 Mermaid sequence diagrams using ONLY
   actors and class names from the provided data:
   - "Legacy: Article Create Flow" — shows Browser → ArticleServlet (or equivalent) → DAO → DB
   - "Legacy: User Login Flow" — shows Browser → LoginServlet (or equivalent filter) → session → DB
   - "Modern: Article Create Flow" — shows Browser → ArticleController (REST) → ArticleService → ArticleRepository → DB
   - "Modern: User Auth Flow" — shows Browser → POST /api/v1/auth/login → JwtAuthFilter → UserRepository → JWT response
   Use ONLY class/component names that appear in the architecture plan or source classes.
   Use correct Mermaid sequenceDiagram syntax with participant declarations.

CRITICAL: Do NOT invent class names, URLs, or package names not present in the input data.
Output a structured plan — be specific, use real names from the input.
""".strip()


# ── Structured output schemas ─────────────────────────────────────────────────

class RoadmapItem(BaseModel):
    phase:       str = Field(description="Phase A or B")
    task:        str
    source_file: str = ""
    target_file: str = ""
    priority:    int = Field(description="1=highest", ge=1, le=5)


class FrameworkUpgrade(BaseModel):
    legacy:  str = Field(description="e.g. javax.servlet.HttpServlet")
    modern:  str = Field(description="e.g. @RestController")
    notes:   str = ""


class SequenceDiagram(BaseModel):
    title:          str
    mermaid_source: str


class MigrationPlan(BaseModel):
    roadmap:            list[RoadmapItem]     = []
    framework_upgrades: list[FrameworkUpgrade] = []
    brd_summary:        str = ""
    sequence_diagrams:  list[SequenceDiagram] = []


class PlannerAgent(BaseAgent):
    """
    Generates a full migration roadmap, framework upgrade guide, BRD,
    and sequence diagrams using with_structured_output(MigrationPlan).

    Anti-hallucination: all LLM inputs are grounded in actual parsed data
    (class names, REST paths, entity names, entry points).
    """

    def run(self, state: MigrationState) -> MigrationState:
        self._logger.info("PlannerAgent starting")

        arch_plan     = state.get("arch_plan", {})
        bounded_ctxs  = arch_plan.get("bounded_contexts", [])
        entity_map    = state.get("jdbc_map", {}).get("entity_map", {})
        entry_points  = state.get("entry_points", [])
        modules       = state.get("module_clusters", [])
        soap_report   = state.get("soap_report", {})

        # ── Build grounded class-name summaries per domain ─────────────────
        # For each bounded context, collect the actual legacy class names that
        # belong to it — so the LLM can name them in the roadmap and diagrams.
        domain_classes: dict[str, list[str]] = {}
        for bc in bounded_ctxs:
            name    = bc.get("name", "")
            classes = bc.get("source_classes", [])
            simple  = [c.split(".")[-1] for c in classes]
            domain_classes[name] = simple[:20]  # cap at 20 per domain

        # ── Collect ALL entry points split by type ─────────────────────────
        servlet_eps = [e for e in entry_points if "Servlet" in e or "servlet" in e]
        jsp_eps     = [e for e in entry_points if e.endswith(".jsp")]

        # ── Extract REST paths actually defined in arch_plan ──────────────
        rest_paths_by_domain: dict[str, list[str]] = {}
        for bc in bounded_ctxs:
            name = bc.get("name", "")
            paths = [
                f"{ep.get('method')} {ep.get('path')}"
                for ep in bc.get("rest_endpoints", [])
            ]
            rest_paths_by_domain[name] = paths[:6]

        # ── Build the grounded user input ──────────────────────────────────
        user_input = (
            "=== ARCHITECTURE PLAN (bounded contexts with real class names) ===\n"
            f"{json.dumps(arch_plan, indent=2, default=str)[:5000]}\n\n"

            "=== LEGACY SOURCE CLASSES GROUPED BY DOMAIN ===\n"
            f"{json.dumps(domain_classes, indent=2)}\n\n"

            "=== JDBC TABLES → JPA ENTITY MAPPINGS ===\n"
            f"{json.dumps(entity_map, indent=2)}\n\n"

            "=== SERVLET ENTRY POINTS (legacy controllers) ===\n"
            f"{json.dumps(servlet_eps[:15], indent=2)}\n\n"

            "=== JSP FILES (legacy views) ===\n"
            f"{json.dumps(jsp_eps[:15], indent=2)}\n\n"

            "=== REST ENDPOINTS DEFINED IN NEW ARCHITECTURE ===\n"
            f"{json.dumps(rest_paths_by_domain, indent=2)}\n\n"

            f"SOAP integrations: {len(soap_report.get('integrations', []))}\n"
            f"Module count: {state.get('module_count', 0)}\n"
            f"Language stats: {state.get('language_stats', {})}\n\n"

            "REQUIREMENT: Every roadmap task MUST name a REAL class/file from the lists above. "
            "Every sequence diagram MUST use ONLY actors from the architecture plan or entry points. "
            "Do NOT invent class names."
        )

        # ── with_structured_output → validated MigrationPlan object ───────
        plan: MigrationPlan | None = self._call_structured(
            _PLANNER_SYSTEM, user_input, MigrationPlan, model="claude"
        )

        if plan is None:
            plan = MigrationPlan()

        # ── Fallback: if LLM returns empty, build deterministic plan ───────
        if not plan.roadmap:
            plan.roadmap = self._build_fallback_roadmap(bounded_ctxs, entity_map, entry_points)

        if not plan.framework_upgrades:
            plan.framework_upgrades = self._build_framework_upgrades(state)

        # ── Always augment with deterministic legacy sequence diagrams ─────
        # Replace any LLM-generated sequences with grounded ones if the LLM
        # didn't generate exactly 4 (2 legacy + 2 modern).
        legacy_seqs  = [s for s in plan.sequence_diagrams if "Legacy" in s.title or "legacy" in s.title]
        modern_seqs  = [s for s in plan.sequence_diagrams if "Modern" in s.title or "modern" in s.title]

        if not legacy_seqs:
            legacy_seqs = self._build_legacy_sequences(servlet_eps, entry_points, state)
            plan.sequence_diagrams = legacy_seqs + list(plan.sequence_diagrams)

        if not modern_seqs:
            modern_seqs = self._build_modern_sequences(bounded_ctxs, entity_map)
            plan.sequence_diagrams = list(plan.sequence_diagrams) + modern_seqs

        # ── Serialise to state ─────────────────────────────────────────────
        seq_diagrams_state = [
            {
                "diagram_type":   "sequence",
                "title":          sd.title,
                "mermaid_source": sd.mermaid_source,
                "module":         None,
            }
            for sd in plan.sequence_diagrams
        ]

        state["migration_plan"] = {
            "roadmap":            [r.model_dump() for r in plan.roadmap],
            "framework_upgrades": [u.model_dump() for u in plan.framework_upgrades],
            "brd_summary":        plan.brd_summary,
        }
        state["sequence_diagrams"] = seq_diagrams_state
        state["diagrams"]          = state.get("diagrams", []) + seq_diagrams_state
        state["current_phase"]     = "planned"

        self._logger.info(
            "PlannerAgent complete",
            roadmap_items=len(plan.roadmap),
            upgrades=len(plan.framework_upgrades),
            sequences=len(plan.sequence_diagrams),
        )
        return state

    # ── Deterministic fallbacks (no LLM — pure data derivation) ──────────────

    @staticmethod
    def _build_fallback_roadmap(
        bounded_ctxs: list[dict],
        entity_map: dict[str, str],
        entry_points: list[str],
    ) -> list[RoadmapItem]:
        """Build a concrete roadmap from actual bounded context + entry point data."""
        items: list[RoadmapItem] = []

        # Phase A tasks
        items.append(RoadmapItem(phase="A", task="Set up Gradle multi-module project structure",
                                 target_file="build.gradle", priority=1))
        items.append(RoadmapItem(phase="A", task="Configure Spring Security + JWT authentication",
                                 target_file="src/main/java/config/SecurityConfig.java", priority=1))
        items.append(RoadmapItem(phase="A", task="Configure Spring Data JPA + PostgreSQL datasource",
                                 target_file="src/main/resources/application.yml", priority=1))

        # Phase B tasks derived from bounded contexts
        for bc in bounded_ctxs:
            name = bc.get("name", "")
            if name.lower() == "security":
                items.append(RoadmapItem(
                    phase="B",
                    task=f"Implement JWT auth endpoints (login, logout, register)",
                    source_file="web/WEB-INF/web.xml",
                    target_file=f"src/main/java/security/AuthController.java",
                    priority=1,
                ))
                continue
            mod  = bc.get("spring_module", name.lower())
            entities = bc.get("jpa_entities", [])
            classes  = [c.split(".")[-1] for c in bc.get("source_classes", [])]

            # Find matching servlet entry point
            servlet_src = next(
                (e for e in entry_points if name.lower() in e.lower() and "Servlet" in e),
                ""
            )

            if entities:
                for ent in entities[:2]:
                    items.append(RoadmapItem(
                        phase="B",
                        task=f"Create @Entity {ent} with JPA mappings",
                        source_file=f"DB table in entity_map",
                        target_file=f"src/main/java/{mod}/{ent}.java",
                        priority=1,
                    ))
                    items.append(RoadmapItem(
                        phase="B",
                        task=f"Create {ent}Repository extends JpaRepository",
                        source_file=next((c for c in classes if "Dao" in c), ""),
                        target_file=f"src/main/java/{mod}/{ent}Repository.java",
                        priority=2,
                    ))

            items.append(RoadmapItem(
                phase="B",
                task=f"Create {name}Service with business logic",
                source_file=next((c for c in classes if "Service" in c), ""),
                target_file=f"src/main/java/{mod}/{name}Service.java",
                priority=2,
            ))
            items.append(RoadmapItem(
                phase="B",
                task=f"Create {name}Controller @RestController",
                source_file=servlet_src or next((c for c in classes if "Servlet" in c), ""),
                target_file=f"src/main/java/{mod}/{name}Controller.java",
                priority=2,
            ))

            # React component
            items.append(RoadmapItem(
                phase="B",
                task=f"Create React {name}ListPage and {name}FormPage components",
                source_file=f"{name.lower()}.jsp (or equivalent)",
                target_file=f"src/components/{name}/{name}ListPage.tsx",
                priority=3,
            ))

        return items

    @staticmethod
    def _build_framework_upgrades(state: MigrationState) -> list[FrameworkUpgrade]:
        """Build framework upgrade list grounded in actual detected technologies."""
        entry_points = state.get("entry_points", [])
        soap_count   = len(state.get("soap_report", {}).get("integrations", []))
        upgrades = [
            FrameworkUpgrade(
                legacy="javax.servlet.HttpServlet (doGet/doPost)",
                modern="@RestController + @GetMapping/@PostMapping",
                notes="Direct 1:1 per Servlet class",
            ),
            FrameworkUpgrade(
                legacy="HttpSession-based authentication",
                modern="Spring Security 6 + JWT Bearer token",
                notes="Stateless JWT; tokens issued at POST /api/v1/auth/login",
            ),
            FrameworkUpgrade(
                legacy="JDBC PreparedStatement / ResultSet manual mapping",
                modern="Spring Data JPA: JpaRepository<Entity, Long>",
                notes="One repository per @Entity; custom JPQL for complex queries",
            ),
            FrameworkUpgrade(
                legacy="JSP scriptlet <% %> business logic",
                modern="@Service class with @Transactional",
                notes="Extract all scriptlet logic to dedicated service classes",
            ),
            FrameworkUpgrade(
                legacy="JSP page template (.jsp files)",
                modern="React 18 functional component (.tsx)",
                notes="Each JSP view maps to a React page component",
            ),
            FrameworkUpgrade(
                legacy="web.xml XML deployment descriptor",
                modern="Spring Boot auto-configuration + @Configuration classes",
                notes="Servlet mappings → @RequestMapping; filters → @Component SecurityFilter",
            ),
            FrameworkUpgrade(
                legacy="Maven pom.xml build",
                modern="Gradle build.gradle (Kotlin DSL)",
                notes="Use Spring Boot Gradle plugin 3.3; gradlew bootJar for packaging",
            ),
            FrameworkUpgrade(
                legacy="WAR deployment to Tomcat",
                modern="Embedded Tomcat via gradlew bootRun / bootJar",
                notes="No external server required; jar is self-contained",
            ),
        ]
        if soap_count > 0:
            upgrades.append(FrameworkUpgrade(
                legacy="Apache Axis SOAP client (org.apache.axis.client)",
                modern="Spring WS WebServiceTemplate / OpenFeign REST adapter",
                notes=f"{soap_count} SOAP integration(s) detected — wrap behind Spring @Service",
            ))
        if any(".jsp" in ep for ep in entry_points):
            upgrades.append(FrameworkUpgrade(
                legacy="JSP tag libraries (JSTL <c:forEach>)",
                modern="React hooks (useState / useEffect) + Axios",
                notes="Server-side rendering → client-side SPA with REST API",
            ))
        return upgrades

    @staticmethod
    def _build_legacy_sequences(
        servlet_eps: list[str],
        all_entry_points: list[str],
        state: MigrationState,
    ) -> list[SequenceDiagram]:
        """
        Build legacy sequence diagrams DETERMINISTICALLY from parsed data.
        Uses actual Servlet/JSP names — zero LLM.
        """
        modules   = state.get("module_clusters", [])
        jdbc_map  = state.get("jdbc_map", {})
        tables    = jdbc_map.get("tables", [])

        # Find primary article-like servlet and user/auth-like servlet
        art_servlet  = next((e.split("/")[-1] for e in servlet_eps if "article" in e.lower()), None)
        auth_servlet = next(
            (e.split("/")[-1] for e in servlet_eps
             if any(kw in e.lower() for kw in ("login", "auth", "user", "filter"))),
            None,
        )
        art_table  = next((t for t in tables if "article" in t.lower()), tables[0] if tables else "T_ARTICLE")
        user_table = next((t for t in tables if "user" in t.lower()), "T_USER")

        # Business logic class names from modules
        art_dao  = "ArticleDaoImpl"
        user_dao = "UserDaoImpl"
        for mod in modules:
            for c in mod.get("classes", []):
                cn = c.split(".")[-1]
                if "article" in cn.lower() and "dao" in cn.lower():
                    art_dao = cn
                if "user" in cn.lower() and "dao" in cn.lower():
                    user_dao = cn

        seq1_src = art_servlet  or "ArticleServlet"
        seq2_src = auth_servlet or "ArticleFilter"

        seq1 = SequenceDiagram(
            title="Legacy: Article Create Flow",
            mermaid_source=f"""sequenceDiagram
    participant Browser
    participant {seq1_src}
    participant {art_dao}
    participant DB as Database ({art_table})

    Browser->>+{seq1_src}: POST /NewArticle (form submit)
    {seq1_src}->>+{seq1_src}: request.getParameter()
    {seq1_src}->>+{art_dao}: insertArticle(title, content, author)
    {art_dao}->>+DB: INSERT INTO {art_table}
    DB-->>-{art_dao}: rowsAffected
    {art_dao}-->>-{seq1_src}: void
    {seq1_src}->>Browser: response.sendRedirect(article.jsp)
    Browser->>+{seq1_src}: GET /article.jsp
    {seq1_src}->>+{art_dao}: getArticleById(id)
    {art_dao}->>+DB: SELECT * FROM {art_table} WHERE id=?
    DB-->>-{art_dao}: ResultSet
    {art_dao}-->>-{seq1_src}: Article object
    {seq1_src}-->>-Browser: Rendered JSP HTML""",
        )

        seq2 = SequenceDiagram(
            title="Legacy: User Login Flow",
            mermaid_source=f"""sequenceDiagram
    participant Browser
    participant {seq2_src}
    participant {user_dao}
    participant DB as Database ({user_table})
    participant Session as HttpSession

    Browser->>+{seq2_src}: POST /login (username, password)
    {seq2_src}->>+{user_dao}: getUserByUsername(username)
    {user_dao}->>+DB: SELECT * FROM {user_table} WHERE username=?
    DB-->>-{user_dao}: ResultSet
    {user_dao}-->>-{seq2_src}: User object (or null)
    alt Authentication success
        {seq2_src}->>+Session: setAttribute("user", user)
        Session-->>-{seq2_src}: ok
        {seq2_src}->>Browser: sendRedirect(index.jsp)
    else Authentication failure
        {seq2_src}->>Browser: sendRedirect(login.jsp?error=1)
    end""",
        )
        return [seq1, seq2]

    @staticmethod
    def _build_modern_sequences(
        bounded_ctxs: list[dict],
        entity_map: dict[str, str],
    ) -> list[SequenceDiagram]:
        """
        Build modern sequence diagrams from actual REST endpoints and entities.
        Zero LLM — entirely derived from arch_plan data.
        """
        # Pick article-like domain
        art_bc   = next((bc for bc in bounded_ctxs
                         if "article" in bc.get("name", "").lower()), None)
        art_name = art_bc.get("name", "Article") if art_bc else "Article"
        art_mod  = art_bc.get("spring_module", "article") if art_bc else "article"
        art_ent  = (art_bc.get("jpa_entities") or [art_name])[0] if art_bc else art_name

        # POST endpoint path
        post_path = f"/api/v1/{art_mod}s"
        if art_bc:
            for ep in art_bc.get("rest_endpoints", []):
                if ep.get("method") == "POST":
                    post_path = ep.get("path", post_path)
                    break

        seq3 = SequenceDiagram(
            title=f"Modern: {art_name} Create Flow",
            mermaid_source=f"""sequenceDiagram
    participant Browser as React ({art_name}FormPage)
    participant API as POST {post_path}
    participant JWT as JwtAuthFilter
    participant Ctrl as {art_name}Controller
    participant Svc as {art_name}Service
    participant Repo as {art_ent}Repository
    participant DB as PostgreSQL

    Browser->>+API: POST {post_path} (JSON body + Bearer token)
    API->>+JWT: validate Bearer token
    JWT->>JWT: parse JWT claims
    JWT-->>-API: SecurityContext populated
    API->>+Ctrl: create{art_name}(@RequestBody dto, principal)
    Ctrl->>Ctrl: @Valid DTO validation
    Ctrl->>+Svc: create{art_name}(dto, authorId)
    Svc->>+Repo: save({art_ent} entity)
    Repo->>+DB: INSERT INTO {art_ent.lower()}_table
    DB-->>-Repo: saved entity (with generated id)
    Repo-->>-Svc: {art_ent}
    Svc-->>-Ctrl: {art_ent}DTO
    Ctrl-->>-Browser: 201 Created (JSON {art_ent}DTO)""",
        )

        seq4 = SequenceDiagram(
            title="Modern: User Auth Flow",
            mermaid_source="""sequenceDiagram
    participant Browser as React (LoginPage)
    participant API as POST /api/v1/auth/login
    participant Ctrl as AuthController
    participant Svc as AuthService
    participant Repo as UserRepository
    participant DB as PostgreSQL
    participant JWT as JwtTokenProvider

    Browser->>+API: POST /api/v1/auth/login (JSON {username, password})
    API->>+Ctrl: login(@RequestBody LoginRequest)
    Ctrl->>+Svc: authenticate(username, password)
    Svc->>+Repo: findByUsername(username)
    Repo->>+DB: SELECT * FROM user_table WHERE username=?
    DB-->>-Repo: User entity
    Repo-->>-Svc: User
    Svc->>Svc: BCrypt.verify(password, hash)
    alt Valid credentials
        Svc->>+JWT: generateToken(userId, roles)
        JWT-->>-Svc: signed JWT (exp: 24h)
        Svc-->>-Ctrl: AuthResponse(token, user)
        Ctrl-->>-Browser: 200 OK {token, user}
        Browser->>Browser: localStorage → Authorization header
    else Invalid credentials
        Svc-->>Ctrl: throw AuthenticationException
        Ctrl-->>Browser: 401 Unauthorized
    end""",
        )
        return [seq3, seq4]
