// src/app/migration/[id]/layout.tsx
"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  GitBranch, ScanLine, BarChart3, ClipboardCheck,
  Code2, Download, ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useMigration } from "@/hooks/useMigration";

const NAV_ITEMS = [
  { step: 1, label: "Scanning",   href: "scanning",   icon: ScanLine,       phase: "parsing"    },
  { step: 2, label: "Analysis",   href: "analysis",   icon: BarChart3,      phase: "designing"  },
  { step: 3, label: "Plan Review",href: "review",     icon: ClipboardCheck, phase: "planned"    },
  { step: 4, label: "Code Gen",   href: "generating", icon: Code2,          phase: "generating" },
  { step: 5, label: "Download",   href: "complete",   icon: Download,       phase: "completed"  },
];

export default function MigrationLayout({ children }: { children: React.ReactNode }) {
  const { id }    = useParams<{ id: string }>();
  const pathname  = usePathname();
  const { migration } = useMigration(id);

  const currentStep = NAV_ITEMS.findIndex((n) =>
    pathname.includes(`/${n.href}`)
  );

  return (
    <div className="min-h-screen flex">
      {/* ── Sidebar ── */}
      <aside className="w-64 min-w-[16rem] bg-[#161b22] border-r border-[#30363d]
                         flex flex-col sticky top-0 h-screen overflow-y-auto">

        {/* Logo */}
        <div className="px-5 py-5 border-b border-[#30363d]">
          <Link href="/" className="flex items-center gap-2 group">
            <GitBranch className="h-5 w-5 text-indigo-400" />
            <span className="text-sm font-semibold text-white">Migration Platform</span>
          </Link>
          {migration && (
            <p className="mt-2 text-xs font-mono text-slate-500 truncate" title={id}>
              {id.slice(0, 8)}…
            </p>
          )}
        </div>

        {/* Progress bar */}
        {migration && (
          <div className="px-5 py-4 border-b border-[#30363d]">
            <div className="flex justify-between text-xs text-slate-500 mb-1.5">
              <span>Overall progress</span>
              <span>{Math.round(migration.progress_pct)}%</span>
            </div>
            <div className="h-1.5 bg-[#21262d] rounded-full overflow-hidden">
              <div
                className="h-full bg-indigo-500 rounded-full transition-all duration-700"
                style={{ width: `${migration.progress_pct}%` }}
              />
            </div>
          </div>
        )}

        {/* Nav steps */}
        <nav className="flex-1 px-3 py-4 space-y-1">
          {NAV_ITEMS.map(({ step, label, href, icon: Icon }, idx) => {
            const isActive  = pathname.includes(`/${href}`);
            const isDone    = idx < currentStep;
            const isLocked  = !migration && idx > 0;

            return (
              <Link
                key={href}
                href={isLocked ? "#" : `/migration/${id}/${href}`}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors",
                  isActive  && "bg-indigo-500/10 text-indigo-400 border border-indigo-500/20",
                  isDone    && !isActive && "text-emerald-400 hover:bg-[#21262d]",
                  !isActive && !isDone  && "text-slate-500 hover:bg-[#21262d] hover:text-slate-300",
                  isLocked  && "pointer-events-none opacity-40",
                )}
              >
                <span className={cn(
                  "flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold",
                  isActive && "bg-indigo-500 text-white",
                  isDone   && !isActive && "bg-emerald-500/20 text-emerald-400",
                  !isActive && !isDone && "bg-[#21262d] text-slate-500",
                )}>
                  {isDone && !isActive ? "✓" : step}
                </span>
                <Icon className="h-4 w-4 flex-shrink-0" />
                <span className="font-medium">{label}</span>
                {isActive && <ChevronRight className="h-3 w-3 ml-auto" />}
              </Link>
            );
          })}
        </nav>

        {/* Status footer */}
        {migration && (
          <div className="px-5 py-4 border-t border-[#30363d]">
            <p className="text-xs text-slate-500">Status</p>
            <p className="text-xs font-mono text-slate-300 mt-0.5 capitalize">
              {migration.status.replace(/_/g, " ")}
            </p>
            {migration.approval_status === "awaiting_approval" && (
              <div className="mt-2 flex items-center gap-1.5">
                <span className="relative flex h-2 w-2">
                  <span className="gate-pulse" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-400" />
                </span>
                <span className="text-xs text-amber-400 font-medium">Awaiting approval</span>
              </div>
            )}
          </div>
        )}
      </aside>

      {/* ── Main content ── */}
      <main className="flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  );
}
