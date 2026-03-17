// src/components/ui/ProgressBar.tsx
import { cn } from "@/lib/utils";

interface Props {
  value:     number;   // 0–100
  className?: string;
  color?:    "indigo" | "emerald" | "amber";
}

const COLORS = {
  indigo:  "bg-indigo-500",
  emerald: "bg-emerald-500",
  amber:   "bg-amber-500",
};

export function ProgressBar({ value, className, color = "indigo" }: Props) {
  return (
    <div className={cn("w-full bg-[#21262d] rounded-full overflow-hidden", className ?? "h-1.5")}>
      <div
        className={cn("h-full rounded-full transition-all duration-700 ease-out", COLORS[color])}
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  );
}
