"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import type { BehavioralAnalysis } from "@/types";
import { MODE_HEADER, MODE_STORAGE_KEY } from "@/lib/mode";
import { thinkingLog } from "@/lib/thinkingLogStore";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function currentMode(): string {
  if (typeof window === "undefined") return "demo";
  try { return localStorage.getItem(MODE_STORAGE_KEY) || "demo"; } catch { return "demo"; }
}

interface UseStreamingOptions {
  pollIntervalMs?: number;
  /** When false, the hook does NOT auto-fire the analysis on mount or
   *  on the polling interval. Used in Paper mode with zero trades. */
  enabled?: boolean;
  /** Context hash — when this string/number changes, the hook re-runs the
   *  analysis. Used to gate AI model re-execution to meaningful state changes
   *  (new trades, watchlist edits, mode flip) rather than every UI re-render. */
  contextHash?: string | number | null;
  /** Debounce window (ms) before re-running analysis after the hash changes.
   *  Prevents thrashing when many context fields update in quick succession. */
  debounceMs?: number;
}

type StreamEvent =
  | { type: "status"; message: string }
  | { type: "token";  text: string }
  | { type: "result"; analysis: BehavioralAnalysis };

interface State {
  analysis: BehavioralAnalysis | null;
  streamingText: string;
  status: string;          // most recent status message
  streaming: boolean;      // true while a stream is active
  loading: boolean;        // alias for streaming, kept for hook compat
}

const INITIAL: State = {
  analysis: null,
  streamingText: "",
  status: "",
  streaming: false,
  loading: false,
};

/**
 * Streams /analyze-behavior-stream from the backend, parsing SSE events
 * and exposing live token-by-token text to the UI plus the final
 * BehavioralAnalysis when the stream completes.
 *
 * The hook keeps a manual ReadableStream reader (not EventSource) because
 * SSE on the spec only supports GET. Our endpoint is POST so we drive the
 * decode loop ourselves.
 */
export function useStreamingAnalysis(
  arg?: number | UseStreamingOptions,
) {
  // Backward-compat: hook used to take a single `pollIntervalMs` number.
  const opts: UseStreamingOptions = typeof arg === "number"
    ? { pollIntervalMs: arg, enabled: true }
    : { enabled: true, ...(arg ?? {}) };
  const enabled = opts.enabled ?? true;
  const pollIntervalMs = opts.pollIntervalMs;
  const contextHash = opts.contextHash ?? null;
  const debounceMs = opts.debounceMs ?? 600;

  const [s, setS] = useState<State>(INITIAL);
  const abortRef = useRef<AbortController | null>(null);
  const lastHashRef = useRef<string | number | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const start = useCallback(async () => {
    // Cancel any in-flight stream first.
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    setS(prev => ({ ...prev, streamingText: "", status: "", streaming: true, loading: true }));

    // Persistent thinking log: append a run header so the user can scroll
    // back through every analysis the AI model has ever produced this session.
    const mode = currentMode() as "demo" | "paper" | "kite";
    const runId = thinkingLog.startRun(mode, `hash=${String(contextHash ?? "init")}`);

    try {
      const r = await fetch(`${BASE}/analyze-behavior-stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          [MODE_HEADER]:  currentMode(),
        },
        credentials: "include",
        body: "{}",
        signal: ac.signal,
      });
      if (!r.ok || !r.body) throw new Error(`stream HTTP ${r.status}`);

      const reader = r.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE events are separated by a blank line.
        let idx;
        while ((idx = buffer.indexOf("\n\n")) >= 0) {
          const rawEvent = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);

          // Only the data: line carries our payload.
          const dataLine = rawEvent.split("\n").find(l => l.startsWith("data: "));
          if (!dataLine) continue;
          const json = dataLine.slice(6).trim();
          if (!json || json === "{}") continue;

          let ev: StreamEvent;
          try {
            ev = JSON.parse(json) as StreamEvent;
          } catch {
            console.error("malformed SSE payload:", json);
            continue;
          }

          if (ev.type === "token") {
            setS(prev => ({ ...prev, streamingText: prev.streamingText + ev.text }));
            thinkingLog.append({ runId, mode, kind: "token", text: ev.text });
          } else if (ev.type === "status") {
            setS(prev => ({ ...prev, status: ev.message }));
            thinkingLog.append({ runId, mode, kind: "status", text: ev.message });
          } else if (ev.type === "result") {
            setS(prev => ({
              ...prev,
              analysis: ev.analysis,
              // Prefer the result's audited log over any partial stream text.
              // thinking_log because it includes the audited 7-step trace
              // formatted consistently with the e4b real-inference path.
              streamingText: ev.analysis.thinking_log ?? prev.streamingText,
            }));
            thinkingLog.append({
              runId, mode, kind: "result",
              text: `Score ${ev.analysis.behavioral_score} · ${ev.analysis.detected_pattern || "Healthy Trading"}`,
            });
          }
        }
      }
    } catch (e: unknown) {
      if ((e as Error).name === "AbortError") return;       // user-cancelled, fine
      console.error("stream failed:", e);
      setS(prev => ({ ...prev, status: "Stream error" }));
      thinkingLog.append({ runId, mode, kind: "error", text: `Stream error: ${(e as Error).message || e}` });
    } finally {
      setS(prev => ({ ...prev, streaming: false, loading: false }));
      if (abortRef.current === ac) abortRef.current = null;
    }
  }, []);

  // Lifecycle + optional polling interval.
  // When `enabled` flips false (e.g. user switched to Paper mode with no
  // trades), abort any in-flight stream and clear the analysis so the
  // dashboard can show its empty state.
  //
  // Crucially: when `contextHash` is supplied, we do NOT auto-fire on mount.
  // The hash-change effect below handles the initial run (the very first
  // hash will differ from `null` → fires once). This prevents the duplicate-
  // run-on-mount problem that re-burned 20+s of CPU on every dashboard load.
  useEffect(() => {
    if (!enabled) {
      abortRef.current?.abort();
      if (debounceRef.current) clearTimeout(debounceRef.current);
      setS(INITIAL);
      lastHashRef.current = null;     // re-arm hash effect for next enable cycle
      return;
    }
    if (contextHash == null) {
      // No hash provided → behave like before (auto-start, optional polling).
      start();
    }
    if (!pollIntervalMs) {
      return () => {
        abortRef.current?.abort();
        if (debounceRef.current) clearTimeout(debounceRef.current);
      };
    }
    const id = setInterval(start, pollIntervalMs);
    return () => {
      clearInterval(id);
      abortRef.current?.abort();
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pollIntervalMs, enabled, contextHash == null]);

  // Context-hash gated re-execution: only re-run analysis when the upstream
  // context object materially changes (new trades, watchlist edits, mode
  // flip). Debounced so a burst of related updates collapses to one run.
  useEffect(() => {
    if (!enabled || contextHash == null) return;
    if (lastHashRef.current === contextHash) return;       // no meaningful change
    lastHashRef.current = contextHash;

    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => { start(); }, debounceMs);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contextHash, debounceMs, enabled]);

  return {
    analysis:      s.analysis,
    streamingText: s.streamingText,
    status:        s.status,
    streaming:     s.streaming,
    loading:       s.loading,
    refresh:       start,
  };
}
