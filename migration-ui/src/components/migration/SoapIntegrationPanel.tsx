// src/components/migration/SoapIntegrationPanel.tsx
"use client";

import { useState } from "react";
import type { SoapIntegration } from "@/types";
import { cn } from "@/lib/utils";
import { Plug, ChevronDown, ChevronUp, AlertTriangle, CheckCircle, Info } from "lucide-react";

interface Props {
  integrations: SoapIntegration[];
  total:        number;
  highRisk:     number;
}

const OPTION_LABELS: Record<string, { label: string; color: string; desc: string }> = {
  A: { label: "REST Adapter",  color: "text-emerald-400", desc: "Wrap Axis client behind Spring Boot @RestController. Zero provider change." },
  B: { label: "Spring WS",     color: "text-blue-400",    desc: "Replace Axis with Spring Web Services WebServiceTemplate. Axis fully removed." },
  C: { label: "OpenFeign REST", color: "text-violet-400", desc: "Declarative REST client — only if provider exposes a REST API." },
};

const COMPLEXITY_STYLES: Record<string, string> = {
  LOW:    "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  MEDIUM: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  HIGH:   "bg-red-500/10 text-red-400 border-red-500/20",
};

function IntegrationCard({ item }: { item: SoapIntegration }) {
  const [open, setOpen] = useState(false);
  const opt = OPTION_LABELS[item.migration_option] ?? OPTION_LABELS.A;

  return (
    <div className="card overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-[#21262d] transition-colors text-left"
      >
        <Plug className="h-4 w-4 text-slate-500 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-white truncate">{item.service_name}</p>
          <p className="text-xs font-mono text-slate-500 truncate">{item.endpoint_url || item.wsdl_url || "No endpoint detected"}</p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className={cn("text-xs font-mono px-2 py-0.5 rounded border", COMPLEXITY_STYLES[item.complexity])}>
            {item.complexity}
          </span>
          <span className={cn("text-xs font-medium", opt.color)}>→ {opt.label}</span>
          {open ? <ChevronUp className="h-4 w-4 text-slate-500" /> : <ChevronDown className="h-4 w-4 text-slate-500" />}
        </div>
      </button>

      {open && (
        <div className="border-t border-[#30363d] px-4 py-4 bg-[#0d1117] space-y-4 animate-fade-in">
          {/* Callsite */}
          <div>
            <p className="text-xs text-slate-500 mb-1">Callsite</p>
            <code className="text-xs font-mono text-slate-300">
              {item.callsite_class}.{item.callsite_method}()
            </code>
          </div>

          {/* Operations */}
          {item.operations?.length > 0 && (
            <div>
              <p className="text-xs text-slate-500 mb-1.5">Operations ({item.operations.length})</p>
              <div className="flex flex-wrap gap-1.5">
                {item.operations.map((op) => (
                  <span key={op} className="text-xs font-mono bg-[#21262d] border border-[#30363d] text-slate-300 px-2 py-0.5 rounded">
                    {op}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Migration options */}
          <div>
            <p className="text-xs text-slate-500 mb-2">Migration Options</p>
            <div className="space-y-2">
              {Object.entries(OPTION_LABELS).map(([key, val]) => (
                <div
                  key={key}
                  className={cn(
                    "flex items-start gap-2 px-3 py-2 rounded-lg border text-xs",
                    item.migration_option === key
                      ? "bg-indigo-500/10 border-indigo-500/30"
                      : "bg-[#21262d] border-[#30363d]"
                  )}
                >
                  {item.migration_option === key
                    ? <CheckCircle className="h-3.5 w-3.5 text-indigo-400 mt-0.5 flex-shrink-0" />
                    : <Info className="h-3.5 w-3.5 text-slate-600 mt-0.5 flex-shrink-0" />
                  }
                  <div>
                    <span className={cn("font-semibold", val.color)}>Option {key}: {val.label}</span>
                    <p className="text-slate-500 mt-0.5">{val.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Implementation notes */}
          {item.implementation_notes && (
            <div className="p-3 bg-[#21262d] rounded-lg text-xs text-slate-400">
              {item.implementation_notes}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function SoapIntegrationPanel({ integrations, total, highRisk }: Props) {
  if (!integrations.length) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <CheckCircle className="h-10 w-10 text-emerald-500 mb-3" />
        <p className="text-white font-medium">No SOAP integrations detected</p>
        <p className="text-slate-500 text-sm mt-1">Your codebase has no org.apache.axis.client usage</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Stats row */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Total SOAP services",    value: total,    color: "text-white" },
          { label: "High-risk integrations", value: highRisk, color: "text-red-400" },
          { label: "Require migration path", value: total,    color: "text-amber-400" },
        ].map(({ label, value, color }) => (
          <div key={label} className="card p-4 text-center">
            <p className={cn("text-2xl font-mono font-bold", color)}>{value}</p>
            <p className="text-xs text-slate-500 mt-0.5">{label}</p>
          </div>
        ))}
      </div>

      {highRisk > 0 && (
        <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-sm text-red-400">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          {highRisk} high-risk integration{highRisk !== 1 ? "s" : ""} detected — review carefully before approving
        </div>
      )}

      {/* Integration cards */}
      <div className="space-y-2">
        {integrations.map((item, i) => (
          <IntegrationCard key={`${item.service_name}-${i}`} item={item} />
        ))}
      </div>
    </div>
  );
}
