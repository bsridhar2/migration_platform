// src/components/migration/DiagramViewer.tsx
"use client";

import { useEffect, useRef, useState } from "react";
import type { DiagramArtifact } from "@/types";
import { cn } from "@/lib/utils";
import { ZoomIn, ZoomOut, RotateCcw, Download } from "lucide-react";

interface Props {
  diagrams: DiagramArtifact[];
}

export function DiagramViewer({ diagrams }: Props) {
  const [active, setActive] = useState(0);
  const [zoom,   setZoom]   = useState(1);
  const containerRef = useRef<HTMLDivElement>(null);

  const diagram = diagrams[active];

  useEffect(() => {
    if (!diagram || !containerRef.current) return;

    let cancelled = false;

    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad:  false,
          theme:        "dark",
          fontFamily:   "Inter, sans-serif",
          themeVariables: {
            background:      "#161b22",
            primaryColor:    "#1f3a5f",
            primaryTextColor: "#e6edf3",
            lineColor:       "#58a6ff",
            secondaryColor:  "#21262d",
            tertiaryColor:   "#30363d",
          },
        });

        const id = `mermaid-${active}-${Date.now()}`;
        const { svg } = await mermaid.render(id, diagram.mermaid_source);
        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg;
        }
      } catch (err) {
        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = `
            <div class="p-4 text-red-400 text-xs font-mono">
              Failed to render diagram: ${err instanceof Error ? err.message : "Unknown error"}
              <pre class="mt-2 text-slate-500 whitespace-pre-wrap text-xs">${diagram.mermaid_source}</pre>
            </div>
          `;
        }
      }
    })();

    return () => { cancelled = true; };
  }, [active, diagram]);

  const downloadSvg = () => {
    const svg = containerRef.current?.querySelector("svg");
    if (!svg) return;
    const blob = new Blob([svg.outerHTML], { type: "image/svg+xml" });
    const url  = URL.createObjectURL(blob);
    const a    = Object.assign(document.createElement("a"), {
      href: url, download: `${diagram.title.replace(/\s+/g, "-").toLowerCase()}.svg`,
    });
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!diagrams.length) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-600 text-sm">
        No diagrams available yet
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Tab bar */}
      <div className="flex gap-1 flex-wrap">
        {diagrams.map((d, i) => (
          <button
            key={i}
            onClick={() => { setActive(i); setZoom(1); }}
            className={cn(
              "px-3 py-1.5 text-xs font-medium rounded-md transition-colors",
              i === active
                ? "bg-indigo-500/20 text-indigo-400 border border-indigo-500/30"
                : "text-slate-500 hover:text-slate-300 hover:bg-[#21262d]"
            )}
          >
            {d.title}
          </button>
        ))}
      </div>

      {/* Diagram panel */}
      <div className="card overflow-hidden">
        {/* Toolbar */}
        <div className="flex items-center justify-between px-4 py-2 border-b border-[#30363d]">
          <span className="text-xs font-mono text-slate-500">{diagram.title}</span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))}
              className="p-1.5 text-slate-500 hover:text-white hover:bg-[#21262d] rounded"
            >
              <ZoomOut className="h-4 w-4" />
            </button>
            <span className="text-xs font-mono text-slate-500 w-10 text-center">
              {Math.round(zoom * 100)}%
            </span>
            <button
              onClick={() => setZoom((z) => Math.min(3, z + 0.25))}
              className="p-1.5 text-slate-500 hover:text-white hover:bg-[#21262d] rounded"
            >
              <ZoomIn className="h-4 w-4" />
            </button>
            <button
              onClick={() => setZoom(1)}
              className="p-1.5 text-slate-500 hover:text-white hover:bg-[#21262d] rounded ml-1"
            >
              <RotateCcw className="h-4 w-4" />
            </button>
            <button
              onClick={downloadSvg}
              className="p-1.5 text-slate-500 hover:text-indigo-400 hover:bg-[#21262d] rounded ml-1"
            >
              <Download className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* SVG canvas */}
        <div className="overflow-auto bg-[#0d1117] p-4 min-h-[300px] max-h-[600px]">
          <div
            ref={containerRef}
            className="mermaid-container transition-transform origin-top-left"
            style={{ transform: `scale(${zoom})` }}
          />
        </div>

        {/* Mermaid source toggle */}
        <details className="border-t border-[#30363d]">
          <summary className="px-4 py-2 text-xs text-slate-600 cursor-pointer hover:text-slate-400 select-none">
            View Mermaid source
          </summary>
          <pre className="px-4 py-3 text-xs font-mono text-slate-500 overflow-x-auto bg-[#0d1117]">
            {diagram.mermaid_source}
          </pre>
        </details>
      </div>
    </div>
  );
}
