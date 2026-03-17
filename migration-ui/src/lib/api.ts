// src/lib/api.ts
// ─── Typed Axios API client for the FastAPI backend ──────────────────────────

import axios, { AxiosInstance } from "axios";
import type {
  ArtifactsResponse,
  ApprovalDecision,
  ApprovalResponse,
  MigrationRecord,
  StartMigrationRequest,
} from "@/types";

const BASE_URL =
  typeof window !== "undefined"
    ? ""                                          // Browser: use Next.js rewrites (/api/*)
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function createClient(): AxiosInstance {
  const client = axios.create({
    baseURL: BASE_URL,
    headers: { "Content-Type": "application/json" },
    timeout: 30_000,
  });

  // Request logging in development
  if (process.env.NODE_ENV === "development") {
    client.interceptors.request.use((config) => {
      console.debug(`[API] ${config.method?.toUpperCase()} ${config.url}`);
      return config;
    });
  }

  // Global error normalisation
  client.interceptors.response.use(
    (res) => res,
    (err) => {
      const detail = err.response?.data?.detail;
      // FastAPI 422 returns detail as an array of validation error objects
      const message = Array.isArray(detail)
        ? detail.map((e: { loc?: string[]; msg?: string }) =>
            `${e.loc?.slice(1).join(".") ?? "field"}: ${e.msg ?? "invalid"}`
          ).join("; ")
        : detail ||
          err.response?.data?.error ||
          err.message ||
          "Unknown error";
      return Promise.reject(new Error(message));
    }
  );

  return client;
}

const http = createClient();

// ── Migrations ───────────────────────────────────────────────────────────────

export const api = {
  /** Start a new migration run. Returns migration_id immediately. */
  startMigration: async (body: StartMigrationRequest): Promise<MigrationRecord> => {
    const { data } = await http.post<MigrationRecord>("/api/migrations", body);
    return data;
  },

  /** Poll migration status (used by SWR). */
  getMigration: async (id: string): Promise<MigrationRecord> => {
    const { data } = await http.get<MigrationRecord>(`/api/migrations/${id}`);
    return data;
  },

  /** Fetch all Phase A artifacts for the review screen. */
  getArtifacts: async (id: string): Promise<ArtifactsResponse> => {
    const { data } = await http.get<ArtifactsResponse>(`/api/migrations/${id}/artifacts`);
    return data;
  },

  /** Approve or reject the migration plan — resumes the LangGraph workflow. */
  submitApproval: async (
    id: string,
    decision: ApprovalDecision
  ): Promise<ApprovalResponse> => {
    const { data } = await http.post<ApprovalResponse>(
      `/api/migrations/${id}/approve`,
      decision
    );
    return data;
  },

  /** Download URL helper — returns a signed URL from the backend. */
  getDownloadUrl: (id: string, artifact: "react" | "spring" | "docs"): string =>
    `${BASE_URL}/api/migrations/${id}/download/${artifact}`,
};

export default api;
