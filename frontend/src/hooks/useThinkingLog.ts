"use client";

import { useSyncExternalStore } from "react";
import { thinkingLog, type ThinkingLogEntry } from "@/lib/thinkingLogStore";

/**
 * useThinkingLog — exposes the append-only persistent AI model log to
 * components. Survives component unmount, route changes, and page reload.
 */
export function useThinkingLog(): {
  entries: ThinkingLogEntry[];
  append: typeof thinkingLog.append;
  startRun: typeof thinkingLog.startRun;
  clear: typeof thinkingLog.clear;
} {
  const entries = useSyncExternalStore(
    thinkingLog.subscribe,
    thinkingLog.getSnapshot,
    thinkingLog.getServerSnapshot,
  );
  return {
    entries,
    append:   thinkingLog.append.bind(thinkingLog),
    startRun: thinkingLog.startRun.bind(thinkingLog),
    clear:    thinkingLog.clear.bind(thinkingLog),
  };
}
