// src/components/ui/Spinner.tsx
import { cn } from "@/lib/utils";

interface Props {
  size?:  "sm" | "md" | "lg";
  color?: string;
}

const SIZES = { sm: "h-4 w-4 border-2", md: "h-7 w-7 border-2", lg: "h-12 w-12 border-3" };

export function Spinner({ size = "md", color }: Props) {
  return (
    <span
      className={cn(
        "inline-block rounded-full animate-spin",
        "border-[#30363d]",
        color ? `border-t-[${color}]` : "border-t-indigo-500",
        SIZES[size]
      )}
      aria-label="Loading…"
    />
  );
}
