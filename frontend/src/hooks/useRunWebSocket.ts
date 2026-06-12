// AgentX — WebSocket Hook
// Connects to /ws/runs/:runId and streams progress events
import { useCallback, useEffect, useRef, useState } from 'react';
import type { ProgressEvent } from '@/types';

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000';

export interface UseRunWebSocketOptions {
  runId: string | null;
  onEvent?: (event: ProgressEvent) => void;
  onComplete?: (event: ProgressEvent) => void;
  onError?: (error: string) => void;
}

export function useRunWebSocket({
  runId,
  onEvent,
  onComplete,
  onError,
}: UseRunWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<ProgressEvent[]>([]);

  const connect = useCallback(() => {
    if (!runId) return;
    const url = `${WS_URL}/ws/runs/${runId}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      // Start keepalive ping every 25s
      const pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send('ping');
      }, 25000);
      (ws as any)._pingInterval = pingInterval;
    };

    ws.onmessage = (msg) => {
      try {
        const event: ProgressEvent = JSON.parse(msg.data);
        if (event.type === 'pong') return;

        setEvents((prev) => [...prev.slice(-200), event]); // keep last 200 events
        onEvent?.(event);

        if (event.type === 'complete') {
          onComplete?.(event);
          ws.close();
        }
        if (event.type === 'error') {
          onError?.(event.error || 'Unknown error');
        }
      } catch {
        // ignore parse errors
      }
    };

    ws.onclose = () => {
      setConnected(false);
      clearInterval((ws as any)._pingInterval);
      // Reconnect after 3s if not intentionally closed
      reconnectTimer.current = setTimeout(() => connect(), 3000);
    };

    ws.onerror = () => {
      setConnected(false);
    };
  }, [runId, onEvent, onComplete, onError]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
      setEvents([]);
    };
  }, [connect]);

  return { connected, events };
}
