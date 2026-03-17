// src/app/migration/[id]/complete/page.tsx
"use client";

import { useParams }   from "next/navigation";
import { useMigration } from "@/hooks/useMigration";
import { api }          from "@/lib/api";
import toast            from "react-hot-toast";
import { Download, FileCode2, Package, FileText, CheckCircle, ArrowLeft } from "lucide-react";
import Link from "next/link";

const ARTIFACTS = [
  {
    key:    "react" as const,
    label:  "React App",
    file:   "react_app.zip",
    icon:   FileCode2,
    color:  "text-blue-400",
    bg:     "bg-blue-500/10 border-blue-500/20",
    desc:   "React 18 + TypeScript + Vite — one component per migrated JSP page",
    items:  ["Functional components with hooks", "Axios service layer", "TypeScript interfaces", "CSS Modules styling"],
  },
  {
    key:    "spring" as const,
    label:  "Spring Boot App",
    file:   "springboot_gradle.zip",
    icon:   Package,
    color:  "text-emerald-400",
    bg:     "bg-emerald-500/10 border-emerald-500/20",
    desc:   "Spring Boot 3.3 + Gradle — controllers, JPA entities, SOAP adapters",
    items:  ["@RestController from servlets", "JpaRepository from JDBC", "SOAP adapters / Spring WS", "Gradle build + gradlew wrapper"],
  },
  {
    key:    "docs" as const,
    label:  "Documentation",
    file:   "migration_docs.zip",
    icon:   FileText,
    color:  "text-violet-400",
    bg:     "bg-violet-500/10 border-violet-500/20",
    desc:   "Architecture diagrams, BRD, migration roadmap, SOAP report",
    items:  ["System architecture diagram", "Sequence diagrams per module", "SOAP integration report", "Framework upgrade guide"],
  },
];

export default function CompletePage() {
  const { id } = useParams<{ id: string }>();
  const { migration } = useMigration(id);

  const handleDownload = (artifact: typeof ARTIFACTS[number]) => {
    const url = api.getDownloadUrl(id, artifact.key);
    const a   = Object.assign(document.createElement("a"), {
      href:     url,
      download: artifact.file,
    });
    a.click();
    toast.success(`Downloading ${artifact.file}…`);
  };

  return (
    <div className="p-8 max-w-4xl mx-auto animate-fade-in">
      {/* Header */}
      <div className="text-center mb-12">
        <div className="flex items-center justify-center mb-5">
          <div className="w-20 h-20 rounded-full bg-emerald-500/10 border-2 border-emerald-500/30
                          flex items-center justify-center">
            <CheckCircle className="h-10 w-10 text-emerald-400" />
          </div>
        </div>
        <p className="text-xs font-mono text-emerald-400 uppercase tracking-widest mb-2">Migration Complete</p>
        <h1 className="text-3xl font-semibold text-white">Your Projects Are Ready</h1>
        <p className="text-slate-400 mt-2 text-sm max-w-lg mx-auto">
          Both projects compile successfully. Download the ZIP files below — run{" "}
          <code className="text-emerald-400 font-mono text-xs">./gradlew build</code> and{" "}
          <code className="text-blue-400 font-mono text-xs">npm run build</code> out of the box.
        </p>
      </div>

      {/* Download cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-10">
        {ARTIFACTS.map((artifact) => {
          const Icon = artifact.icon;
          return (
            <div key={artifact.key} className={`card p-5 border ${artifact.bg} flex flex-col gap-4`}>
              <div className="flex items-center gap-3">
                <div className={`w-10 h-10 rounded-lg ${artifact.bg} flex items-center justify-center`}>
                  <Icon className={`h-5 w-5 ${artifact.color}`} />
                </div>
                <div>
                  <p className="text-sm font-semibold text-white">{artifact.label}</p>
                  <p className="text-xs font-mono text-slate-500">{artifact.file}</p>
                </div>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">{artifact.desc}</p>
              <ul className="space-y-1.5 flex-1">
                {artifact.items.map((item) => (
                  <li key={item} className="flex items-center gap-2 text-xs text-slate-500">
                    <span className={`text-xs ${artifact.color}`}>✓</span>
                    {item}
                  </li>
                ))}
              </ul>
              <button
                onClick={() => handleDownload(artifact)}
                className={`w-full flex items-center justify-center gap-2 py-2.5 rounded-lg
                           border font-medium text-sm transition-colors ${artifact.bg}
                           ${artifact.color} hover:opacity-80`}
              >
                <Download className="h-4 w-4" />
                Download
              </button>
            </div>
          );
        })}
      </div>

      {/* Quick start commands */}
      <div className="card p-6 mb-8">
        <h2 className="text-sm font-semibold text-white mb-4">Quick Start Commands</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-slate-500 mb-2">Spring Boot (Gradle)</p>
            <pre className="bg-[#0d1117] rounded-lg p-3 text-xs font-mono text-emerald-400 overflow-x-auto">
{`unzip springboot_gradle.zip
cd springboot_gradle
./gradlew build
./gradlew bootRun`}
            </pre>
          </div>
          <div>
            <p className="text-xs text-slate-500 mb-2">React + TypeScript</p>
            <pre className="bg-[#0d1117] rounded-lg p-3 text-xs font-mono text-blue-400 overflow-x-auto">
{`unzip react_app.zip
cd react_app
npm install
npm run dev`}
            </pre>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="flex justify-center">
        <Link
          href="/"
          className="flex items-center gap-2 text-sm text-slate-500 hover:text-white transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Start a new migration
        </Link>
      </div>
    </div>
  );
}
