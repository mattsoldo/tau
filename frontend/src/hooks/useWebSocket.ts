'use client';

import { useEffect, useRef, useCallback } from 'react';

export interface FixtureStateChangedEvent {
  type: 'fixture_state_changed';
  fixture_id: number;
  brightness: number;
  color_temp: number | null;
  timestamp: string;
}

export interface GroupStateChangedEvent {
  type: 'group_state_changed';
  group_id: number;
  brightness: number;
  color_temp: number | null;
  timestamp: string;
}

export type WebSocketEvent = FixtureStateChangedEvent | GroupStateChangedEvent;

interface UseWebSocketOptions {
  onFixtureStateChanged?: (event: FixtureStateChangedEvent) => void;
  onGroupStateChanged?: (event: GroupStateChangedEvent) => void;
  onConnected?: () => void;
  onDisconnected?: () => void;
}

/**
 * Custom hook for WebSocket connection to receive real-time state updates
 *
 * @param options - Callbacks for handling WebSocket events
 * @returns Object with connection status and reconnect function
 */
export function useWebSocket(options: UseWebSocketOptions = {}) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const mountedRef = useRef(true);
  const isConnectedRef = useRef(false);

  // Store callbacks in refs to avoid reconnection on callback changes
  const optionsRef = useRef(options);
  optionsRef.current = options;

  // Calculate exponential backoff delay for reconnection attempts
  const getReconnectDelay = useCallback(() => {
    const baseDelay = 1000; // 1 second
    const maxDelay = 30000; // 30 seconds
    const delay = Math.min(baseDelay * Math.pow(2, reconnectAttemptsRef.current), maxDelay);
    return delay;
  }, []);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    // Determine WebSocket URL based on current location
    const protocol = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = typeof window !== 'undefined' ? window.location.host : 'localhost:8000';
    const wsUrl = `${protocol}//${host}/ws`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) {
          ws.close();
          return;
        }
        isConnectedRef.current = true;
        reconnectAttemptsRef.current = 0; // Reset backoff on successful connection
        optionsRef.current.onConnected?.();

        // Subscribe to state change events
        ws.send(JSON.stringify({
          action: 'subscribe',
          event_types: ['fixture_state_changed', 'group_state_changed']
        }));

        // Set up ping interval for keepalive
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ action: 'ping' }));
          }
        }, 30000);

        ws.addEventListener('close', () => {
          if (pingIntervalRef.current) {
            clearInterval(pingIntervalRef.current);
            pingIntervalRef.current = null;
          }
        });
      };

      ws.onmessage = (event) => {
        if (!mountedRef.current) return;

        try {
          const data = JSON.parse(event.data) as WebSocketEvent;

          switch (data.type) {
            case 'fixture_state_changed':
              optionsRef.current.onFixtureStateChanged?.(data);
              break;
            case 'group_state_changed':
              optionsRef.current.onGroupStateChanged?.(data);
              break;
            default:
              // Log unexpected event types in development
              if (process.env.NODE_ENV === 'development') {
                console.warn('[WebSocket] Unknown event type:', (data as any).type, data);
              }
              break;
          }
        } catch (error) {
          // Log parse errors in development to aid debugging
          if (process.env.NODE_ENV === 'development') {
            console.error('[WebSocket] Failed to parse message:', event.data, error);
          }
        }
      };

      ws.onclose = () => {
        if (!mountedRef.current) return;
        isConnectedRef.current = false;
        optionsRef.current.onDisconnected?.();

        // Attempt to reconnect with exponential backoff
        const delay = getReconnectDelay();
        reconnectAttemptsRef.current += 1;
        reconnectTimeoutRef.current = setTimeout(() => {
          if (mountedRef.current) {
            connect();
          }
        }, delay);
      };

      ws.onerror = () => {
        // Error will trigger onclose, which handles reconnection
      };

    } catch {
      // Connection failed, try again with exponential backoff
      const delay = getReconnectDelay();
      reconnectAttemptsRef.current += 1;
      reconnectTimeoutRef.current = setTimeout(() => {
        if (mountedRef.current) {
          connect();
        }
      }, delay);
    }
  }, [getReconnectDelay]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
      pingIntervalRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    isConnectedRef.current = false;
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      disconnect();
    };
  }, [connect, disconnect]);

  return {
    isConnected: isConnectedRef.current,
    reconnect: connect,
  };
}
