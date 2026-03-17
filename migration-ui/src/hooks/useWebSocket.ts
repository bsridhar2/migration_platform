// src/hooks/useWebSocket.ts
// ─── WebSocket hook for real-time migration progress ─────────────────────────

"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { WebSocketMessage } from "@/types";

const WS_BASE =
  typeof window !== "undefined"
    ? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`
    : process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

type ConnectionState = "connecting" | "connected" | "disconnected" | "error";

interface UseWebSocketReturn {
  lastMessage:     WebSocketMessage | null;
  connectionState: ConnectionState;
  disconnect:      () => void;
}

export function useWebSocket(migrationId: string | null): UseWebSocketReturn {
  const [lastMessage, setLastMessage]     = useState<WebSocketMessage | null>(null);
  const [connectionState, setConnectionState] = useState<ConnectionState>("disconnected");
  const wsRef    = useRef<WebSocket | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retries  = useRef(0);
  const MAX_RETRIES = 5;

  const connect = useCallback(() => {
    if (!migrationId) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setConnectionState("connecting");
    const ws = new WebSocket(`${WS_BASE}/api/migrations/${migrationId}/ws`);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnectionState("connected");
      retries.current = 0;
    };

    ws.onmessage = (event) => {
      try {
        const msg: WebSocketMessage = JSON.parse(event.data);
        setLastMessage(msg);

        // Auto-disconnect on terminal states
        if (msg.status === "completed" || msg.status === "failed") {
          ws.close(1000, "Terminal state reached");
        }
      } catch {
        // ignore malformed messages
      }
    };

    ws.onerror = () => setConnectionState("error");

    ws.onclose = (ev) => {
      setConnectionState("disconnected");
      // Exponential backoff reconnect (unless clean close or max retries)
      if (ev.code !== 1000 && retries.current < MAX_RETRIES) {
        const delay = Math.min(1000 * 2 ** retries.current, 30_000);
        retries.current += 1;
        retryRef.current = setTimeout(connect, delay);
      }
    };
  }, [migrationId]);

  useEffect(() => {
    connect();
    return () => {
      if (retryRef.current) clearTimeout(retryRef.current);
      wsRef.current?.close(1000, "Component unmounted");
    };
  }, [connect]);

  const disconnect = useCallback(() => {
    if (retryRef.current) clearTimeout(retryRef.current);
    wsRef.current?.close(1000, "Manual disconnect");
  }, []);

  return { lastMessage, connectionState, disconnect };
}
