// src/components/ui/StatusBadge.tsx
import { cn, statusColor, statusLabel } from "@/lib/utils";
import type { MigrationStatus } from "@/types";

interface Props {
  status: MigrationStatus | string;
  size?:  "sm" | "md";
}

const DOT_COLORS: Record<string, string> = {
  completed:         "bg-emerald-400",
  failed:            "bg-red-400",
  awaiting_approval: "bg-amber-400 animate-pulse",
  validating:        "bg-violet-400 animate-pulse",
  generating:        "bg-blue-400 animate-pulse",
  building:          "bg-blue-400 animate-pulse",
};

export function StatusBadge({ status, size = "md" }: Props) {
  const dotColor = DOT_COLORS[status] ?? "bg-slate-400";

  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 font-medium rounded-full border",
      size === "sm" ? "text-xs px-2 py-0.5" : "text-xs px-2.5 py-1",
      "bg-[#21262d] border-[#30363d] text-slate-300"
    )}>
      <span className={cn("w-1.5 h-1.5 rounded-full flex-shrink-0", dotColor)} />
      {statusLabel(status)}
    </span>
  );
}
