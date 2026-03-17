// src/hooks/useMigration.ts
// ─── SWR hook for migration status polling ───────────────────────────────────

"use client";

import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { api } from "@/lib/api";
import type {
  ApprovalDecision,
  ArtifactsResponse,
  MigrationRecord,
} from "@/types";

// ── Status polling ────────────────────────────────────────────────────────────

export function useMigration(migrationId: string | null) {
  const { data, error, isLoading, mutate } = useSWR<MigrationRecord>(
    migrationId ? `/migration/${migrationId}` : null,
    () => api.getMigration(migrationId!),
    {
      refreshInterval: (data) => {
        // Only stop on truly terminal states.
        // "awaiting_approval" is NOT terminal — after approval is submitted the
        // workflow resumes and status will advance, so we must keep polling.
        if (data?.status === "completed" || data?.status === "failed") {
          return 0;
        }
        return 2000;  // Poll every 2 s while active
      },
      revalidateOnFocus: false,
    }
  );

  return { migration: data, error, isLoading, refresh: mutate };
}

// ── Artifact fetching ─────────────────────────────────────────────────────────

export function useArtifacts(migrationId: string | null) {
  const { data, error, isLoading } = useSWR<ArtifactsResponse>(
    migrationId ? `/artifacts/${migrationId}` : null,
    () => api.getArtifacts(migrationId!),
    { revalidateOnFocus: false }
  );

  return { artifacts: data, error, isLoading };
}

// ── Approval mutation ─────────────────────────────────────────────────────────

export function useApproval(migrationId: string) {
  const { trigger, isMutating, error } = useSWRMutation(
    `/approve/${migrationId}`,
    async (_key: string, { arg }: { arg: ApprovalDecision }) =>
      api.submitApproval(migrationId, arg)
  );

  return { approve: trigger, isSubmitting: isMutating, error };
}
