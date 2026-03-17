// src/app/migration/[id]/generating/page.tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { useMigration }   from "@/hooks/useMigration";
import { useWebSocket }   from "@/hooks/useWebSocket";
import { ProgressBar }    from "@/components/ui/ProgressBar";
import { StatusBadge }    from "@/components/ui/StatusBadge";
import { Spinner }        from "@/components/ui/Spinner";
import { api }            from "@/lib/api";
import toast              from "react-hot-toast";
import { Code2, AlertTriangle, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";

// Load Monaco editor client-side only (heavy bundle)
const MonacoEditor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => <div className="flex items-center justify-center h-64"><Spinner /></div>,
});

const GEN_STEPS = [
  { key: "validating",  label: "Multi-LLM validation (Claude + GPT-4o)",  pct: 85 },
  { key: "generating",  label: "Generating React components + Spring Boot", pct: 92 },
  { key: "building",    label: "Build verification (./gradlew + npm build)", pct: 98 },
  { key: "completed",   label: "Packaging downloadable artifacts",           pct: 100 },
];

const SAMPLE_FILES = [
  { label: "OrderController.java", lang: "java",       content: `@RestController
@RequestMapping("/api/v1/orders")
@RequiredArgsConstructor
@Slf4j
public class OrderController {

    private final OrderService orderService;

    @GetMapping("/{id}")
    public ResponseEntity<OrderDto> getOrder(@PathVariable String id) {
        log.info("GET /orders/{}", id);
        return ResponseEntity.ok(orderService.findById(id));
    }

    @PostMapping
    public ResponseEntity<OrderDto> createOrder(
            @Valid @RequestBody CreateOrderRequest req) {
        return ResponseEntity.status(201)
               .body(orderService.create(req));
    }
}` },
  { label: "OrderPage.tsx", lang: "typescript", content: `import { useState, useEffect } from "react";
import { orderService }        from "@/services/orderService";
import type { Order }          from "@/types/api";

export default function OrderPage() {
  const [orders,  setOrders]  = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    orderService.getAll()
      .then(setOrders)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div>Loading orders…</div>;

  return (
    <ul className="space-y-2">
      {orders.map((o) => (
        <li key={o.id} className="p-4 border rounded-lg">
          <p className="font-semibold">{o.id}</p>
          <p className="text-sm text-gray-500">{o.status}</p>
        </li>
      ))}
    </ul>
  );
}` },
  { label: "build.gradle", lang: "gradle", content: `plugins {
    id 'org.springframework.boot' version '3.3.2'
    id 'io.spring.dependency-management' version '1.1.5'
    id 'java'
}

group   = 'com.migrated'
version = '0.0.1-SNAPSHOT'
java    { sourceCompatibility = JavaVersion.VERSION_21 }

repositories { mavenCentral() }

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.ws:spring-ws-core'
    runtimeOnly    'org.postgresql:postgresql'
    compileOnly    'org.projectlombok:lombok'
    annotationProcessor 'org.projectlombok:lombok'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}` },
];

export default function GeneratingPage() {
  const { id }   = useParams<{ id: string }>();
  const router   = useRouter();
  const { migration, refresh } = useMigration(id);
  const { lastMessage }        = useWebSocket(id);
  const [activeFile, setActiveFile] = useState(0);
  const [isRetrying, setIsRetrying] = useState(false);

  // Detect "stuck" state: if status is still awaiting_approval >8s after
  // arriving on this page, the graph resume probably failed (e.g. server
  // restarted before the fix was applied and the old checkpoint was lost).
  const arrivedAtRef = useRef<number>(Date.now());
  const [isStuck, setIsStuck] = useState(false);

  useEffect(() => { if (lastMessage) refresh(); }, [lastMessage, refresh]);

  useEffect(() => {
    if (migration?.status === "completed") {
      setTimeout(() => router.push(`/migration/${id}/complete`), 1500);
    }
  }, [migration?.status, id, router]);

  // Check for stuck state every second
  useEffect(() => {
    if (migration?.status !== "awaiting_approval") {
      setIsStuck(false);
      return;
    }
    const timer = setInterval(() => {
      if (Date.now() - arrivedAtRef.current > 8000) {
        setIsStuck(true);
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [migration?.status]);

  const handleReApprove = async () => {
    setIsRetrying(true);
    try {
      await api.submitApproval(id, { status: "approved", comment: "Re-approved after resume" });
      toast.success("Re-submitted approval — generation starting…");
      setIsStuck(false);
      arrivedAtRef.current = Date.now();
      refresh();
    } catch (err: any) {
      toast.error(err.message || "Re-approval failed");
    } finally {
      setIsRetrying(false);
    }
  };

  const pct      = migration?.progress_pct ?? 85;
  const curStep  = GEN_STEPS.findLast((s) => pct >= s.pct - 5);

  return (
    <div className="p-8 max-w-5xl mx-auto animate-fade-in">
      <div className="mb-8">
        <p className="text-xs font-mono text-emerald-400 uppercase tracking-widest mb-2">
          Phase B — Code Generation
        </p>
        <h1 className="text-2xl font-semibold text-white">Generating Your Projects</h1>
        <p className="text-slate-400 mt-1 text-sm">
          React 18 + TypeScript components and Spring Boot 3.3 (Gradle) classes are being
          generated in parallel. Each file is verified to compile before delivery.
        </p>
      </div>

      {/* ── Stuck-state recovery banner ── */}
      {isStuck && (
        <div className="mb-6 flex items-start gap-3 p-4 bg-amber-500/10 border border-amber-500/30 rounded-xl">
          <AlertTriangle className="h-5 w-5 text-amber-400 flex-shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-amber-400">Generation not started</p>
            <p className="text-xs text-amber-300/70 mt-0.5">
              The server may have restarted after your approval was submitted, which clears
              the in-memory workflow state. Click <strong>Re-submit Approval</strong> to
              resume code generation.
            </p>
          </div>
          <button
            onClick={handleReApprove}
            disabled={isRetrying}
            className="flex items-center gap-2 px-4 py-2 bg-amber-500 hover:bg-amber-400
                       disabled:opacity-50 text-black text-xs font-semibold rounded-lg
                       transition-colors flex-shrink-0"
          >
            {isRetrying
              ? <><span className="h-3.5 w-3.5 border-2 border-black/30 border-t-black rounded-full animate-spin" /> Submitting…</>
              : <><RefreshCw className="h-3.5 w-3.5" /> Re-submit Approval</>
            }
          </button>
        </div>
      )}

      {/* Progress */}
      <div className="card p-6 mb-6">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-medium text-white">Generation Progress</span>
          <StatusBadge status={migration?.status ?? "generating"} />
        </div>
        <ProgressBar value={pct} className="h-2.5" color="emerald" />

        <div className="mt-5 space-y-3">
          {GEN_STEPS.map((step) => {
            const done   = pct >= step.pct;
            const active = curStep?.key === step.key;
            return (
              <div key={step.key} className="flex items-center gap-3 text-sm">
                <span className={cn(
                  "w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0",
                  done   && "bg-emerald-500 text-white",
                  active && !done && "bg-indigo-500 text-white animate-pulse",
                  !done  && !active && "bg-[#21262d] text-slate-600",
                )}>
                  {done ? "✓" : ""}
                </span>
                <span className={cn(
                  done   && "text-emerald-400",
                  active && !done && "text-white",
                  !done  && !active && "text-slate-600",
                )}>
                  {step.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Monaco code preview */}
      <div className="card overflow-hidden">
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[#30363d] bg-[#0d1117]">
          <Code2 className="h-4 w-4 text-slate-500" />
          <span className="text-xs text-slate-500 font-medium">Generated file preview</span>
          <div className="ml-4 flex gap-1">
            {SAMPLE_FILES.map(({ label }, i) => (
              <button
                key={label}
                onClick={() => setActiveFile(i)}
                className={cn(
                  "text-xs px-2.5 py-1 rounded font-mono transition-colors",
                  activeFile === i
                    ? "bg-[#21262d] text-white"
                    : "text-slate-600 hover:text-slate-400"
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <MonacoEditor
          height="380px"
          language={SAMPLE_FILES[activeFile].lang}
          value={SAMPLE_FILES[activeFile].content}
          theme="vs-dark"
          options={{
            readOnly:        true,
            minimap:         { enabled: false },
            fontSize:        13,
            lineNumbers:     "on",
            scrollBeyondLastLine: false,
            fontFamily:      "'JetBrains Mono', 'Fira Code', monospace",
          }}
        />
      </div>

      {migration?.status === "completed" && (
        <div className="mt-4 flex items-center gap-2 p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-lg text-emerald-400 text-sm animate-fade-in">
          <span className="text-lg">✓</span>
          Build verified! Redirecting to download screen…
        </div>
      )}

      {/* ── Failed / unrecoverable banner ── */}
      {migration?.status === "failed" && (
        <div className="mt-4 p-5 bg-red-500/10 border border-red-500/30 rounded-xl">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-red-400 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-semibold text-red-400 mb-1">Generation failed</p>
              {migration.error_message && (
                <p className="text-xs font-mono text-red-300/80 mb-3 leading-relaxed">
                  {migration.error_message}
                </p>
              )}
              <a
                href="/"
                className="inline-flex items-center gap-2 px-4 py-2 bg-red-500/20
                           hover:bg-red-500/30 border border-red-500/30 text-red-300
                           text-xs font-medium rounded-lg transition-colors"
              >
                ← Start a new migration
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
