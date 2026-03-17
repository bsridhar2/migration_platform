// src/app/page.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { GitBranch, ArrowRight, Zap, Shield, Code2, Database } from "lucide-react";
import toast from "react-hot-toast";
import { api } from "@/lib/api";

const FEATURES = [
  { icon: Zap,      title: "9 AI Agents",        desc: "Parallel analysis — repo, parse, graph, SOAP, arch, plan, validate, codegen, test" },
  { icon: Shield,   title: "Human Approval Gate", desc: "Zero code generated until you review and approve the full migration plan" },
  { icon: Code2,    title: "Gradle Output",        desc: "Spring Boot 3.3 (Gradle) + React 18 + TypeScript — fully buildable" },
  { icon: Database, title: "SOAP Detection",       desc: "Axis clients auto-detected with 3 migration options: REST adapter, Spring WS, OpenFeign" },
];

export default function HomePage() {
  const router  = useRouter();
  const [url,    setUrl]    = useState("");
  const [branch, setBranch] = useState("main");
  const [busy,   setBusy]   = useState(false);

  const handleStart = async () => {
    if (!url.trim()) { toast.error("Please enter a Git repository URL"); return; }
    setBusy(true);
    try {
      const migration = await api.startMigration({ repo_url: url.trim(), branch });
      toast.success("Migration started!");
      router.push(`/migration/${migration.migration_id}/scanning`);
    } catch (err: any) {
      toast.error(err.message || "Failed to start migration");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="min-h-screen flex flex-col">
      {/* ── Hero ── */}
      <div className="flex-1 flex flex-col items-center justify-center px-4 py-20">
        <div className="w-full max-w-2xl animate-slide-up">

          {/* Tag */}
          <div className="flex items-center gap-2 mb-6 justify-center">
            <span className="text-xs font-mono font-bold tracking-widest uppercase text-indigo-400">
              Enterprise AI Migration Platform
            </span>
          </div>

          {/* Headline */}
          <h1 className="text-4xl sm:text-5xl font-light text-center text-white leading-tight mb-4">
            Java Monolith →{" "}
            <span className="font-bold text-indigo-400">React + Spring Boot</span>
          </h1>
          <p className="text-center text-slate-400 mb-10 text-lg leading-relaxed">
            Paste your Git URL. The platform clones, analyses, generates architecture
            diagrams, and — after your approval — delivers fully buildable projects.
          </p>

          {/* Input card */}
          <div className="card p-6 space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">
                Git Repository URL
              </label>
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleStart()}
                placeholder="https://github.com/your-org/legacy-java-app.git"
                className="w-full bg-[#0d1117] border border-[#30363d] rounded-lg px-4 py-3
                           text-slate-100 placeholder:text-slate-600 font-mono text-sm
                           focus:outline-none focus:border-indigo-500 transition-colors"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">
                Branch
              </label>
              <input
                type="text"
                value={branch}
                onChange={(e) => setBranch(e.target.value)}
                className="w-full bg-[#0d1117] border border-[#30363d] rounded-lg px-4 py-3
                           text-slate-100 font-mono text-sm
                           focus:outline-none focus:border-indigo-500 transition-colors"
              />
            </div>

            <button
              onClick={handleStart}
              disabled={busy || !url.trim()}
              className="w-full flex items-center justify-center gap-2 bg-indigo-600
                         hover:bg-indigo-500 disabled:bg-indigo-900 disabled:text-indigo-600
                         text-white font-semibold py-3 px-6 rounded-lg transition-colors"
            >
              {busy ? (
                <>
                  <span className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Starting migration…
                </>
              ) : (
                <>
                  <GitBranch className="h-4 w-4" />
                  Start Migration
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </button>
          </div>
        </div>

        {/* ── Feature grid ── */}
        <div className="w-full max-w-3xl mt-16 grid grid-cols-1 sm:grid-cols-2 gap-4 animate-fade-in">
          {FEATURES.map(({ icon: Icon, title, desc }) => (
            <div key={title} className="card p-5 flex gap-4 hover:border-[#484f58] transition-colors">
              <div className="mt-0.5 flex-shrink-0 w-9 h-9 rounded-lg bg-indigo-500/10
                              flex items-center justify-center">
                <Icon className="h-5 w-5 text-indigo-400" />
              </div>
              <div>
                <p className="font-semibold text-white text-sm">{title}</p>
                <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
