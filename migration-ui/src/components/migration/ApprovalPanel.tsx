// src/components/migration/ApprovalPanel.tsx
"use client";

import { useState } from "react";
import type { ArtifactsResponse, ApprovalDecision } from "@/types";
import { DiagramViewer }        from "./DiagramViewer";
import { SoapIntegrationPanel } from "./SoapIntegrationPanel";
import { cn }                   from "@/lib/utils";
import {
  BarChart3, Plug, ListTodo, FileText, GitBranch,
  CheckCircle, XCircle, AlertTriangle, Layers, ShieldCheck,
} from "lucide-react";

type ReviewTab = "architecture" | "sequences" | "soap" | "plan" | "framework" | "contexts";

interface Props {
  artifacts:     ArtifactsResponse;
  onApprove:     (decision: ApprovalDecision) => Promise<void>;
  isSubmitting:  boolean;
}

// Fallback static framework map — shown only when backend returns no upgrades
const STATIC_FRAMEWORK_MAP = [
  { from: "javax.servlet.HttpServlet",  to: "@RestController + @RequestMapping",      notes: "" },
  { from: "doGet() / doPost()",         to: "@GetMapping / @PostMapping",              notes: "" },
  { from: "HttpSession auth",           to: "Spring Security 6 + JWT Bearer token",   notes: "" },
  { from: "JDBC PreparedStatement",     to: "JpaRepository<Entity, ID>",               notes: "" },
  { from: "ResultSet manual mapping",   to: "@Entity + @Column JPA mapping",           notes: "" },
  { from: "JSP <% scriptlet %>",        to: "@Service with @Transactional",            notes: "" },
  { from: "JSP page template",          to: "React 18 functional .tsx component",     notes: "" },
  { from: "org.apache.axis.client",     to: "Spring WS / OpenFeign / REST adapter",   notes: "" },
  { from: "web.xml XML config",         to: "Spring Boot @Configuration classes",     notes: "" },
  { from: "pom.xml Maven",              to: "build.gradle Kotlin DSL (Gradle 8)",      notes: "" },
  { from: "WAR deployment",             to: "gradlew bootJar — embedded Tomcat",       notes: "" },
];

const TABS: { id: ReviewTab; label: string; icon: React.ElementType }[] = [
  { id: "architecture", label: "Architecture",      icon: BarChart3   },
  { id: "contexts",     label: "Bounded Contexts",  icon: Layers      },
  { id: "sequences",    label: "Sequence Diagrams",  icon: GitBranch   },
  { id: "soap",         label: "SOAP Integrations",  icon: Plug        },
  { id: "plan",         label: "Migration Plan",     icon: ListTodo    },
  { id: "framework",    label: "Framework Upgrades", icon: FileText    },
];

// Helper: read bounded contexts from artifacts if arch_plan is exposed
type BoundedContext = {
  name: string;
  description: string;
  spring_module: string;
  jpa_entities: string[];
  react_components: string[];
  source_classes: string[];
  rest_endpoints: { method: string; path: string; auth: boolean }[];
};

export function ApprovalPanel({ artifacts, onApprove, isSubmitting }: Props) {
  const [tab,     setTab]     = useState<ReviewTab>("architecture");
  const [comment, setComment] = useState("");
  const [viewed,  setViewed]  = useState<Set<ReviewTab>>(new Set());

  const markViewed = (t: ReviewTab) => setViewed((v) => new Set([...v, t]));
  const handleTabClick = (t: ReviewTab) => { setTab(t); markViewed(t); };

  const plan      = artifacts.migration_plan;
  const soap      = artifacts.soap_report;

  // Split diagrams into architecture (legacy + modern) and sequences
  const allDiagrams  = artifacts.diagrams ?? [];
  const archDiagrams = allDiagrams.filter(
    (d) => d.diagram_type === "system_architecture" || d.diagram_type === "legacy_architecture"
  );
  const sequences = [
    ...(artifacts.sequence_diagrams ?? []),
    ...allDiagrams.filter((d) => d.diagram_type === "sequence"),
  ];

  // Bounded contexts from artifacts (arch_plan is included in ArtifactsResponse)
  const archPlan = (artifacts as any).arch_plan ?? {};
  const boundedContexts: BoundedContext[] = archPlan.bounded_contexts ?? [];

  // Framework upgrades — prefer backend data, fall back to static list
  const backendUpgrades: { legacy: string; modern: string; notes?: string }[] =
    plan?.framework_upgrades ?? [];
  const frameworkRows = backendUpgrades.length > 0 ? backendUpgrades : STATIC_FRAMEWORK_MAP;

  // Require at least 3 of 6 tabs visited before enabling approve
  const canApprove = viewed.size >= 3;

  return (
    <div className="flex flex-col gap-6">
      {/* Warning banner */}
      <div className="flex items-start gap-3 p-4 bg-amber-500/10 border border-amber-500/20 rounded-xl">
        <AlertTriangle className="h-5 w-5 text-amber-400 flex-shrink-0 mt-0.5" />
        <div className="text-sm">
          <p className="font-semibold text-amber-400">Human Approval Required</p>
          <p className="text-amber-300/70 mt-0.5">
            Review all tabs below before approving.{" "}
            <strong>Zero code will be generated until you approve.</strong>
            {" "}Rejection regenerates the architecture plan from scratch.
          </p>
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-[#30363d] overflow-x-auto">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => handleTabClick(id)}
            className={cn(
              "flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap",
              tab === id
                ? "border-indigo-500 text-indigo-400"
                : "border-transparent text-slate-500 hover:text-slate-300"
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
            {viewed.has(id) && (
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="min-h-[400px]">

        {/* ── Architecture Diagrams (Legacy + Modern) ── */}
        {tab === "architecture" && (
          archDiagrams.length > 0
            ? <DiagramViewer diagrams={archDiagrams} />
            : <TabEmpty label="Architecture diagrams" />
        )}

        {/* ── Bounded Contexts ── */}
        {tab === "contexts" && (
          boundedContexts.length > 0 ? (
            <div className="space-y-4">
              <p className="text-xs text-slate-500 mb-3">
                {boundedContexts.length} bounded context{boundedContexts.length !== 1 ? "s" : ""} derived from source code analysis
              </p>
              <div className="grid gap-4">
                {boundedContexts.map((bc) => (
                  <div key={bc.name} className="card p-5 space-y-3">
                    <div className="flex items-center gap-3">
                      {bc.name.toLowerCase() === "security"
                        ? <ShieldCheck className="h-4 w-4 text-amber-400 flex-shrink-0" />
                        : <Layers className="h-4 w-4 text-indigo-400 flex-shrink-0" />
                      }
                      <div>
                        <h4 className="text-sm font-semibold text-white">{bc.name}</h4>
                        <p className="text-xs text-slate-400">{bc.description}</p>
                      </div>
                      <span className="ml-auto text-xs font-mono text-slate-500 bg-[#21262d] px-2 py-0.5 rounded">
                        module: {bc.spring_module}
                      </span>
                    </div>

                    <div className="grid grid-cols-2 gap-3 text-xs">
                      {/* JPA Entities */}
                      {bc.jpa_entities?.length > 0 && (
                        <div>
                          <p className="text-slate-500 font-medium mb-1">JPA Entities</p>
                          <div className="flex flex-wrap gap-1">
                            {bc.jpa_entities.map((e) => (
                              <span key={e} className="bg-blue-500/10 text-blue-400 px-1.5 py-0.5 rounded font-mono">{e}</span>
                            ))}
                          </div>
                        </div>
                      )}
                      {/* React Components */}
                      {bc.react_components?.length > 0 && (
                        <div>
                          <p className="text-slate-500 font-medium mb-1">React Components</p>
                          <div className="flex flex-wrap gap-1">
                            {bc.react_components.map((c) => (
                              <span key={c} className="bg-emerald-500/10 text-emerald-400 px-1.5 py-0.5 rounded font-mono">{c}</span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* REST Endpoints */}
                    {bc.rest_endpoints?.length > 0 && (
                      <div>
                        <p className="text-xs text-slate-500 font-medium mb-1">REST Endpoints</p>
                        <div className="space-y-1 max-h-32 overflow-y-auto">
                          {bc.rest_endpoints.map((ep, i) => (
                            <div key={i} className="flex items-center gap-2 font-mono text-xs">
                              <span className={cn(
                                "px-1.5 py-0.5 rounded text-[10px] font-bold",
                                ep.method === "GET"    && "bg-blue-500/20 text-blue-300",
                                ep.method === "POST"   && "bg-emerald-500/20 text-emerald-300",
                                ep.method === "PUT"    && "bg-amber-500/20 text-amber-300",
                                ep.method === "DELETE" && "bg-red-500/20 text-red-300",
                                ep.method === "PATCH"  && "bg-purple-500/20 text-purple-300",
                              )}>
                                {ep.method}
                              </span>
                              <span className="text-slate-300">{ep.path}</span>
                              {!ep.auth && (
                                <span className="text-xs text-slate-600 ml-auto">public</span>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Source Classes count */}
                    {bc.source_classes?.length > 0 && (
                      <p className="text-xs text-slate-600">
                        Legacy source classes: {bc.source_classes.length} (
                        {bc.source_classes.slice(0, 3).map(c => c.split(".").pop()).join(", ")}
                        {bc.source_classes.length > 3 ? `, +${bc.source_classes.length - 3} more` : ""})
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ) : <TabEmpty label="Bounded context details" />
        )}

        {/* ── Sequence Diagrams ── */}
        {tab === "sequences" && (
          sequences.length > 0
            ? <DiagramViewer diagrams={sequences} />
            : <TabEmpty label="Sequence diagrams" />
        )}

        {/* ── SOAP Integrations ── */}
        {tab === "soap" && (
          <SoapIntegrationPanel
            integrations={soap?.integrations ?? []}
            total={soap?.total ?? 0}
            highRisk={soap?.high_risk ?? 0}
          />
        )}

        {/* ── Migration Plan ── */}
        {tab === "plan" && plan && (
          <div className="space-y-6">
            <div className="card p-5">
              <h3 className="text-sm font-semibold text-white mb-4">
                Migration Roadmap ({plan.roadmap?.length ?? 0} tasks)
              </h3>
              <div className="space-y-2 max-h-[500px] overflow-y-auto pr-1">
                {plan.roadmap?.map((item, i) => (
                  <div key={i} className="flex gap-3 items-start text-sm p-3 bg-[#0d1117] rounded-lg">
                    <span className={cn(
                      "flex-shrink-0 text-xs font-mono px-1.5 py-0.5 rounded",
                      item.phase === "A" ? "bg-blue-500/10 text-blue-400" : "bg-emerald-500/10 text-emerald-400"
                    )}>
                      Phase {item.phase}
                    </span>
                    <div className="flex-1">
                      <p className="text-white">{item.task}</p>
                      {(item.source_file || item.target_file) && (
                        <p className="text-xs font-mono text-slate-500 mt-0.5">
                          {item.source_file && <span className="text-red-400">{item.source_file}</span>}
                          {item.source_file && item.target_file && <span className="text-slate-600"> → </span>}
                          {item.target_file && <span className="text-emerald-400">{item.target_file}</span>}
                        </p>
                      )}
                    </div>
                    <span className={cn(
                      "flex-shrink-0 text-xs font-bold",
                      item.priority === 1 ? "text-red-400" :
                      item.priority === 2 ? "text-amber-400" : "text-slate-500"
                    )}>
                      P{item.priority}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ── Framework Upgrades ── */}
        {tab === "framework" && (
          <div className="card overflow-hidden">
            <div className="px-4 py-3 bg-[#21262d] border-b border-[#30363d]">
              <p className="text-xs text-slate-400">
                {backendUpgrades.length > 0
                  ? `${backendUpgrades.length} upgrade patterns detected from your codebase`
                  : "Standard JSP/Servlet → Spring Boot 3.3 + React 18 migration patterns"
                }
              </p>
            </div>
            <table className="w-full text-sm">
              <thead className="bg-[#21262d]">
                <tr>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider w-2/5">Legacy</th>
                  <th className="px-2 py-3 w-4" />
                  <th className="text-left px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider w-2/5">Modern (Gradle)</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider">Notes</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#21262d]">
                {frameworkRows.map((row, i) => (
                  <tr key={i} className="hover:bg-[#21262d]/50">
                    <td className="px-4 py-3 font-mono text-xs text-red-400">
                      {"legacy" in row ? row.legacy : (row as any).from}
                    </td>
                    <td className="px-2 py-3 text-slate-600 text-center">→</td>
                    <td className="px-4 py-3 font-mono text-xs text-emerald-400">
                      {"modern" in row ? row.modern : (row as any).to}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500">
                      {"notes" in row ? row.notes : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Approval footer */}
      <div className="card p-6 space-y-4 border-t-2 border-amber-500/30">
        <div>
          <label className="block text-sm font-medium text-white mb-1.5">
            Review Comment (optional)
          </label>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            rows={3}
            placeholder="Add notes for the development team…"
            className="w-full bg-[#0d1117] border border-[#30363d] rounded-lg px-4 py-3
                       text-slate-300 placeholder:text-slate-600 text-sm
                       focus:outline-none focus:border-indigo-500 transition-colors resize-none"
          />
        </div>

        {!canApprove && (
          <p className="text-xs text-slate-500">
            Please review at least 3 tabs before approving ({viewed.size}/3 viewed)
          </p>
        )}

        <div className="flex gap-3">
          <button
            onClick={() => onApprove({ status: "rejected", comment })}
            disabled={isSubmitting}
            className="flex items-center gap-2 px-5 py-2.5 border border-red-500/30 text-red-400
                       hover:bg-red-500/10 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
          >
            <XCircle className="h-4 w-4" />
            Reject — Regenerate Plan
          </button>

          <button
            onClick={() => onApprove({ status: "approved", comment })}
            disabled={isSubmitting || !canApprove}
            className="flex items-center gap-2 flex-1 justify-center px-5 py-2.5
                       bg-emerald-600 hover:bg-emerald-500 disabled:bg-emerald-900
                       disabled:text-emerald-700 text-white rounded-lg text-sm font-semibold
                       transition-colors"
          >
            {isSubmitting ? (
              <><span className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Processing…</>
            ) : (
              <><CheckCircle className="h-4 w-4" /> Approve &amp; Generate Code</>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

function TabEmpty({ label }: { label: string }) {
  return (
    <div className="flex items-center justify-center py-20 text-slate-600 text-sm">
      {label} not yet available
    </div>
  );
}
