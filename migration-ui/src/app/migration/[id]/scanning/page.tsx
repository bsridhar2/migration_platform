// src/app/migration/[id]/scanning/page.tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useMigration } from "@/hooks/useMigration";
import { ProgressBar }  from "@/components/ui/ProgressBar";
import { StatusBadge }  from "@/components/ui/StatusBadge";
import { cn } from "@/lib/utils";

// Keys must match MigrationStatus values from types/index.ts exactly
const PHASE_STEPS = [
  { key: "ingesting",         label: "Cloning repository",          pct: 10  },
  { key: "parsing",           label: "Parsing & embedding files",    pct: 35  },
  { key: "graphing",          label: "Building dependency graph",    pct: 55  },
  { key: "detecting",         label: "Detecting SOAP integrations",  pct: 65  },
  { key: "designing",         label: "Designing architecture",       pct: 75  },
  { key: "planning",          label: "Generating migration plan",    pct: 85  },
  { key: "awaiting_approval", label: "Ready for review",             pct: 100 },
];

// Covers every FileType enum value emitted by the backend
const FILE_TYPE_CONFIG: Record<string, { label: string; color: string; bg: string; border: string; dot: string }> = {
  JAVA:       { label: "Java",        color: "text-orange-400",  bg: "bg-orange-500/10",  border: "border-orange-500/20",  dot: "bg-orange-400"  },
  JSP:        { label: "JSP",         color: "text-blue-400",    bg: "bg-blue-500/10",    border: "border-blue-500/20",    dot: "bg-blue-400"    },
  JS:         { label: "JavaScript",  color: "text-yellow-400",  bg: "bg-yellow-500/10",  border: "border-yellow-500/20",  dot: "bg-yellow-400"  },
  HTML:       { label: "HTML",        color: "text-amber-400",   bg: "bg-amber-500/10",   border: "border-amber-500/20",   dot: "bg-amber-400"   },
  CSS:        { label: "CSS",         color: "text-purple-400",  bg: "bg-purple-500/10",  border: "border-purple-500/20",  dot: "bg-purple-400"  },
  XML:        { label: "XML",         color: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/20", dot: "bg-emerald-400" },
  WSDL:       { label: "WSDL",        color: "text-cyan-400",    bg: "bg-cyan-500/10",    border: "border-cyan-500/20",    dot: "bg-cyan-400"    },
  SQL:        { label: "SQL",         color: "text-rose-400",    bg: "bg-rose-500/10",    border: "border-rose-500/20",    dot: "bg-rose-400"    },
  PROPERTIES: { label: "Properties",  color: "text-slate-400",   bg: "bg-slate-500/10",   border: "border-slate-500/20",   dot: "bg-slate-400"   },
  OTHER:      { label: "Other",       color: "text-slate-500",   bg: "bg-slate-600/10",   border: "border-slate-600/20",   dot: "bg-slate-500"   },
};

function fmtSecs(secs: number): string {
  if (secs <= 0) return "0s";
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function useElapsed() {
  const [secs, setSecs] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setSecs((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, []);
  return fmtSecs(secs);
}

export default function ScanningPage() {
  const { id }    = useParams<{ id: string }>();
  const router    = useRouter();
  const { migration, refresh } = useMigration(id);
  const { lastMessage } = useWebSocket(id);

  const [lastUpdateTime, setLastUpdateTime] = useState<Date | null>(null);

  // stepStartRef[status] = epoch ms when that step first became active
  const stepStartRef = useRef<Record<string, number>>({});
  // stepElapsed[status] = live running seconds for the currently active step
  const [stepElapsed,   setStepElapsed]   = useState<Record<string, number>>({});
  // stepDurations[status] = final seconds snapshotted when that step completed
  const [stepDurations, setStepDurations] = useState<Record<string, number>>({});
  const prevStatusRef = useRef<string | null>(null);

  const elapsed = useElapsed();

  // Refresh SWR on WS message
  useEffect(() => {
    if (lastMessage) {
      refresh();
      setLastUpdateTime(new Date());
    }
  }, [lastMessage, refresh]);

  // Track per-step elapsed time; snapshot final duration on step transition
  useEffect(() => {
    const status = migration?.status;
    if (!status) return;

    const prev = prevStatusRef.current;

    // Step changed → lock in the final duration for the outgoing step
    if (prev && prev !== status) {
      const start = stepStartRef.current[prev];
      if (start) {
        const finalSecs = Math.floor((Date.now() - start) / 1000);
        setStepDurations((d) => ({ ...d, [prev]: finalSecs }));
      }
    }
    prevStatusRef.current = status;

    // Initialise start time for the new active step (idempotent)
    if (!stepStartRef.current[status]) {
      stepStartRef.current[status] = Date.now();
    }

    // Tick a live counter for the active step every second
    const timer = setInterval(() => {
      const start = stepStartRef.current[status];
      if (start) {
        setStepElapsed((prev) => ({
          ...prev,
          [status]: Math.floor((Date.now() - start) / 1000),
        }));
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [migration?.status]);

  // Auto-navigate when analysis is ready
  useEffect(() => {
    if (migration?.status === "awaiting_approval") {
      router.push(`/migration/${id}/analysis`);
    }
  }, [migration?.status, id, router]);

  const currentPct     = migration?.progress_pct ?? 0;
  const statusIdx      = PHASE_STEPS.findIndex((s) => s.key === migration?.status);
  const currentStepIdx =
    statusIdx !== -1
      ? statusIdx
      : PHASE_STEPS.findLastIndex((s) => currentPct >= s.pct - 10);

  const isActive = migration?.status &&
    !["awaiting_approval", "completed", "failed"].includes(migration.status);

  // Build file type rows from *total* cloned counts (visible as soon as repo is indexed)
  const totalCounts    = migration?.total_file_counts ?? {};
  const embeddedCounts = migration?.file_counts       ?? {};
  const fileTypeEntries = Object.entries(totalCounts)
    .filter(([, total]) => total > 0)
    .sort(([, a], [, b]) => b - a);

  return (
    <div className="p-8 max-w-2xl mx-auto animate-fade-in">
      <div className="mb-8">
        <p className="text-xs font-mono text-indigo-400 uppercase tracking-widest mb-2">
          Phase A — Analysis
        </p>
        <h1 className="text-2xl font-semibold text-white">Scanning Repository</h1>
        <p className="text-slate-400 mt-1 text-sm">
          No code is generated during this phase. All 9 agents analyse your codebase and
          build a migration plan for your review.
        </p>
      </div>

      {/* Live activity banner */}
      {isActive && (
        <div className="flex items-center gap-3 mb-5 px-4 py-3 rounded-lg border border-indigo-500/30 bg-indigo-500/5">
          <span className="relative flex h-2.5 w-2.5 flex-shrink-0">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-indigo-500" />
          </span>
          <span className="text-xs text-indigo-300 font-medium">
            LLM agents are actively processing your codebase
          </span>
          <span className="ml-auto text-xs text-slate-500 font-mono tabular-nums">
            {elapsed}
          </span>
        </div>
      )}

      {/* Overall progress */}
      <div className="card p-6 mb-6">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-medium text-white">Overall Progress</span>
          <StatusBadge status={migration?.status ?? "started"} />
        </div>
        <ProgressBar value={currentPct} className="h-2" />
        <div className="flex items-center justify-between mt-2">
          <p className="text-xs text-slate-500">{Math.round(currentPct)}% complete</p>
          {lastUpdateTime && (
            <p className="text-xs text-slate-600">
              last update {lastUpdateTime.toLocaleTimeString()}
            </p>
          )}
        </div>
      </div>

      {/* ── Agent pipeline with per-step timings ── */}
      <div className="card p-6 mb-6">
        <h2 className="text-sm font-semibold text-white mb-4">Agent Pipeline</h2>
        <div className="space-y-3">
          {PHASE_STEPS.map((step, idx) => {
            const done   = idx < currentStepIdx;
            const active = idx === currentStepIdx;

            // Completed steps → show final snapshotted duration
            // Active step     → show live running duration
            const displaySecs = done
              ? (stepDurations[step.key] ?? null)
              : active
              ? (stepElapsed[step.key] ?? null)
              : null;
            const timeLabel = displaySecs != null && displaySecs > 0
              ? fmtSecs(displaySecs)
              : null;

            return (
              <div key={step.key} className="flex items-center gap-3">
                {/* Step circle */}
                <div className={cn(
                  "w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0",
                  done              && "bg-emerald-500 text-white",
                  active && !done   && "bg-indigo-500 text-white animate-pulse",
                  !done  && !active && "bg-[#21262d] text-slate-600",
                )}>
                  {done ? "✓" : idx + 1}
                </div>

                {/* Label */}
                <span className={cn(
                  "text-sm flex-1",
                  done              && "text-emerald-400",
                  active && !done   && "text-white font-medium",
                  !done  && !active && "text-slate-600",
                )}>
                  {step.label}
                </span>

                {/* Right: time pill + bounce dots */}
                <div className="flex items-center gap-2">
                  {timeLabel && (
                    <span className={cn(
                      "text-xs font-mono tabular-nums px-2 py-0.5 rounded-full border",
                      done   && "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
                      active && !done && "text-indigo-300 bg-indigo-500/10 border-indigo-500/20",
                    )}>
                      {timeLabel}
                    </span>
                  )}
                  {active && (
                    <span className="flex gap-1">
                      {[0, 1, 2].map((i) => (
                        <span
                          key={i}
                          className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-bounce"
                          style={{ animationDelay: `${i * 150}ms` }}
                        />
                      ))}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── File-type breakdown: cloned from GitHub + embedded ── */}
      {fileTypeEntries.length > 0 && (
        <div className="card p-6 mb-6">
          <div className="flex items-center justify-between mb-1">
            <h2 className="text-sm font-semibold text-white">Files Cloned &amp; Embedded</h2>
            <span className="text-xs text-slate-500 tabular-nums">
              {fileTypeEntries.reduce((sum, [, n]) => sum + n, 0)} cloned
              {" · "}
              {fileTypeEntries.reduce((sum, [type]) => sum + (embeddedCounts[type] ?? 0), 0)} embedded
            </span>
          </div>
          <p className="text-xs text-slate-600 mb-4">
            Cloned = all files pulled from GitHub. Embedded = parsed &amp; indexed in the vector store.
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {fileTypeEntries.map(([type, total]) => {
              const cfg      = FILE_TYPE_CONFIG[type] ?? FILE_TYPE_CONFIG.OTHER;
              const embedded = embeddedCounts[type] ?? 0;
              const pct      = total > 0 ? Math.round((embedded / total) * 100) : 0;
              return (
                <div
                  key={type}
                  className={cn("px-3 py-3 rounded-lg border", cfg.bg, cfg.border)}
                >
                  {/* Header row */}
                  <div className="flex items-center gap-2 mb-2">
                    <span className={cn("w-2 h-2 rounded-full flex-shrink-0", cfg.dot)} />
                    <p className={cn("text-xs font-semibold truncate", cfg.color)}>
                      {cfg.label}
                    </p>
                  </div>

                  {/* Cloned count (large) */}
                  <p className="text-2xl font-mono font-bold text-white leading-none">
                    {total}
                  </p>
                  <p className="text-xs text-slate-500 mt-0.5 mb-3">cloned from GitHub</p>

                  {/* Embedded progress */}
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs text-slate-500">embedded</span>
                      <span className={cn("text-xs font-mono tabular-nums", cfg.color)}>
                        {embedded}/{total}
                      </span>
                    </div>
                    <div className="h-1.5 bg-[#21262d] rounded-full overflow-hidden">
                      <div
                        className={cn("h-full rounded-full transition-all duration-500", cfg.dot)}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <p className="text-xs text-slate-600 mt-1 text-right tabular-nums">{pct}%</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Summary stats */}
      {migration && (
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: "Files",  value: migration.chunk_count ? "indexed" : "scanning…" },
            { label: "Chunks", value: migration.chunk_count ?? "–" },
            { label: "SOAP",   value: migration.soap_integration_count ?? "–" },
          ].map(({ label, value }) => (
            <div key={label} className="card p-4 text-center">
              <p className="text-lg font-mono font-bold text-white">{String(value)}</p>
              <p className="text-xs text-slate-500 mt-0.5">{label}</p>
            </div>
          ))}
        </div>
      )}

      {/* Error state */}
      {migration?.status === "failed" && migration.error_message && (
        <div className="mt-6 p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
          <p className="text-sm font-semibold text-red-400 mb-1">Migration failed</p>
          <p className="text-xs font-mono text-red-300">{migration.error_message}</p>
        </div>
      )}
    </div>
  );
}
