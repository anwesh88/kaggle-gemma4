/**
 * thinkingLogStore.ts — append-only Fin AI audit log, persisted across
 * component remounts and unrelated state updates.
 *
 * Lightweight pub/sub (no Redux/Zustand) so components can subscribe with
 * useSyncExternalStore. New runs append a "STEP" entry with a timestamp; the
 * log NEVER resets — even rerunning analysis just appends a new run header.
 *
 * Persistence: localStorage, capped at the last 200 entries.
 */

export interface ThinkingLogEntry {
  id: string;             // ulid-like
  ts: number;             // epoch ms
  step?: string;          // "STEP 1" etc, when streamed from backend
  text: string;
  kind: "status" | "token" | "step" | "result" | "user" | "error";
  mode?: "demo" | "paper" | "kite";
  runId?: string;         // groups entries from the same analysis run
}

const STORAGE_KEY = "finsight.thinkingLog.v1";
const MAX_ENTRIES = 200;

type Listener = () => void;
const listeners = new Set<Listener>();

let entries: ThinkingLogEntry[] = load();

function load(): ThinkingLogEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.slice(-MAX_ENTRIES) : [];
  } catch {
    return [];
  }
}

function persist() {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries.slice(-MAX_ENTRIES)));
  } catch {/* quota: drop silently */}
}

function emit() {
  listeners.forEach(l => l());
}

function newId() {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export const thinkingLog = {
  subscribe(l: Listener) { listeners.add(l); return () => { listeners.delete(l); }; },
  getSnapshot() { return entries; },
  getServerSnapshot() { return entries; },

  append(entry: Omit<ThinkingLogEntry, "id" | "ts"> & { ts?: number; id?: string }) {
    const full: ThinkingLogEntry = {
      id: entry.id || newId(),
      ts: entry.ts || Date.now(),
      ...entry,
    };
    entries = [...entries, full].slice(-MAX_ENTRIES);
    persist();
    emit();
    return full.id;
  },

  startRun(mode: "demo" | "paper" | "kite", note: string) {
    const runId = newId();
    this.append({ runId, mode, kind: "status", text: `── New analysis run (${mode.toUpperCase()}) · ${note}` });
    return runId;
  },

  clear() {
    entries = [];
    persist();
    emit();
  },
};
