// src/app/migration/[id]/analysis/page.tsx
"use client";

import { useParams, useRouter } from "next/navigation";
import { useArtifacts, useMigration } from "@/hooks/useMigration";
import { DiagramViewer }       from "@/components/migration/DiagramViewer";
import { SoapIntegrationPanel } from "@/components/migration/SoapIntegrationPanel";
import { Spinner }             from "@/components/ui/Spinner";
import { ArrowRight, BarChart3, Plug, Network, ChevronRight } from "lucide-react";

type Tab = "architecture" | "soap" | "modules";

export default function AnalysisPage() {
  const { id }   = useParams<{ id: string }>();
  const router   = useRouter();
  const { migration }           = useMigration(id);
  const { artifacts, isLoading } = useArtifacts(id);

  const [activeTab, setActiveTab] = require("react").useState<Tab>("architecture");

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full py-32">
        <Spinner size="lg" />
      </div>
    );
  }

  const diagrams   = artifacts?.diagrams ?? [];
  const soap       = artifacts?.soap_report ?? { integrations: [], total: 0, high_risk: 0 };
  const modules    = migration ? [] : [];

  const tabs = [
    { id: "architecture", label: "Architecture Diagrams", icon: BarChart3, count: diagrams.length },
    { id: "soap",         label: "SOAP Integrations",     icon: Plug,      count: soap.total },
    { id: "modules",      label: "Module Clusters",        icon: Network,   count: 0 },
  ] as const;

  return (
    <div className="p-8 max-w-5xl mx-auto animate-fade-in">
      <div className="flex items-center justify-between mb-8">
        <div>
          <p className="text-xs font-mono text-indigo-400 uppercase tracking-widest mb-2">Phase A — Analysis</p>
          <h1 className="text-2xl font-semibold text-white">Codebase Analysis</h1>
          <p className="text-slate-400 mt-1 text-sm">
            Review the detected architecture, SOAP integrations, and module clusters before proceeding.
          </p>
        </div>
        <button
          onClick={() => router.push(`/migration/${id}/review`)}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white
                     font-medium px-5 py-2.5 rounded-lg transition-colors text-sm"
        >
          Review Plan
          <ArrowRight className="h-4 w-4" />
        </button>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-[#30363d] mb-6">
        {tabs.map(({ id: tabId, label, icon: Icon, count }) => (
          <button
            key={tabId}
            onClick={() => setActiveTab(tabId as Tab)}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tabId
                ? "border-indigo-500 text-indigo-400"
                : "border-transparent text-slate-500 hover:text-slate-300"
            }`}
          >
            <Icon className="h-4 w-4" />
            {label}
            {count > 0 && (
              <span className="ml-1 text-xs bg-[#21262d] text-slate-400 px-1.5 py-0.5 rounded-full">
                {count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "architecture" && (
        diagrams.length > 0
          ? <DiagramViewer diagrams={diagrams} />
          : <EmptyState message="Architecture diagrams are being generated…" />
      )}

      {activeTab === "soap" && (
        <SoapIntegrationPanel
          integrations={soap.integrations}
          total={soap.total}
          highRisk={soap.high_risk}
        />
      )}

      {activeTab === "modules" && (
        <div className="card p-6">
          <p className="text-sm text-slate-400">
            Module cluster data will be available after the dependency graph is built.
          </p>
        </div>
      )}
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <Spinner size="md" />
      <p className="text-slate-500 text-sm mt-4">{message}</p>
    </div>
  );
}
