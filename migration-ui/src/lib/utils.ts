// src/lib/utils.ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge Tailwind classes safely — handles conditionals and conflicts. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** Format a date string to locale-friendly display. */
export function formatDate(iso: string): string {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(iso));
}

/** Convert a status string to a human-readable label. */
export function statusLabel(status: string): string {
  return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Return a colour class based on migration status. */
export function statusColor(status: string): string {
  const map: Record<string, string> = {
    completed:         "text-emerald-400",
    failed:            "text-red-400",
    awaiting_approval: "text-amber-400",
    validating:        "text-violet-400",
    generating:        "text-blue-400",
  };
  return map[status] ?? "text-slate-400";
}

/** Clamp a number between min and max. */
export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}
