// src/app/migration/[id]/review/page.tsx
"use client";

import { useParams, useRouter } from "next/navigation";
import { useArtifacts, useApproval } from "@/hooks/useMigration";
import { ApprovalPanel } from "@/components/migration/ApprovalPanel";
import { Spinner }       from "@/components/ui/Spinner";
import { Download }      from "lucide-react";
import { api }           from "@/lib/api";
import toast             from "react-hot-toast";
import type { ApprovalDecision } from "@/types";

export default function ReviewPage() {
  const { id }   = useParams<{ id: string }>();
  const router   = useRouter();
  const { artifacts, isLoading, error } = useArtifacts(id);
  const { approve, isSubmitting }        = useApproval(id);

  const handleApproval = async (decision: ApprovalDecision) => {
    try {
      await approve(decision);
      if (decision.status === "approved") {
        toast.success("Plan approved! Code generation starting…");
        router.push(`/migration/${id}/generating`);
      } else {
        toast("Plan rejected. Regenerating architecture…", { icon: "🔄" });
        router.push(`/migration/${id}/scanning`);
      }
    } catch (err: any) {
      toast.error(err.message || "Failed to submit approval");
    }
  };

  const handleDownloadDiagrams = () => {
    if (!artifacts?.diagrams?.length) { toast.error("No diagrams to download"); return; }
    // Build SVG bundle (in real app would call backend for ZIP)
    const content = artifacts.diagrams
      .map((d) => `<!-- ${d.title} -->\n${d.mermaid_source}`)
      .join("\n\n");
    const blob = new Blob([content], { type: "text/plain" });
    const url  = URL.createObjectURL(blob);
    Object.assign(document.createElement("a"), {
      href: url,
      download: `migration-plan-${id.slice(0, 8)}.md`,
    }).click();
    URL.revokeObjectURL(url);
    toast.success("Diagrams downloaded");
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full py-32">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error || !artifacts) {
    return (
      <div className="p-8 max-w-2xl mx-auto">
        <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
          {error?.message || "Failed to load migration artifacts. The analysis may still be running."}
        </div>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-5xl mx-auto animate-fade-in">
      <div className="flex items-start justify-between mb-8">
        <div>
          <p className="text-xs font-mono text-amber-400 uppercase tracking-widest mb-2">⛔ Phase 6 — Approval Gate</p>
          <h1 className="text-2xl font-semibold text-white">Migration Plan Review</h1>
          <p className="text-slate-400 mt-1 text-sm">
            Review architecture, SOAP integrations, roadmap, and framework upgrades.
            Download artifacts for offline review before approving.
          </p>
        </div>
        <button
          onClick={handleDownloadDiagrams}
          className="flex items-center gap-2 px-4 py-2 border border-[#30363d] text-slate-400
                     hover:text-white hover:border-[#484f58] rounded-lg text-sm transition-colors"
        >
          <Download className="h-4 w-4" />
          Download Plan
        </button>
      </div>

      <ApprovalPanel
        artifacts={artifacts}
        onApprove={handleApproval}
        isSubmitting={isSubmitting}
      />
    </div>
  );
}
