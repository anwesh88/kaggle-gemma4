"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import type { BehavioralAnalysis } from "@/types";
import { useThinkingLog } from "@/hooks/useThinkingLog";

interface Props {
  log: string | null;
  inferenceTime?: number;
  /** Live text from the SSE stream — when present, takes precedence over `log` */
  streamingText?: string;
  /** True while tokens are still arriving from the backend */
  streaming?: boolean;
  /** Most recent status line from the stream. */
  streamStatus?: string;
  /** Full analysis — used to render clickable evidence per step */
  analysis?: BehavioralAnalysis | null;
}

/**
 * Map a thinking-log line to a "step kind" so we know which slice of the
 * analysis to surface as evidence when the user clicks it. Returns null
 * for non-step lines (no evidence to show).
 */
type StepKind = "vow" | "pattern" | "score" | "nudge" | "lang" | "stress" | "sebi" | null;

function stepKind(line: string): StepKind {
  if (/STEP 1/.test(line)) return "vow";
  if (/STEP 2/.test(line)) return "pattern";
  if (/STEP 3/.test(line)) return "score";
  if (/STEP 4/.test(line)) return "nudge";
  if (/STEP 5/.test(line)) return "lang";
  if (/STEP 6/.test(line)) return "stress";
  if (/STEP 7/.test(line)) return "sebi";
  return null;
}

// Colour-code each STEP line differently
function stepColor(line: string): string {
  if (line.includes("STEP 1")) return "#7C3AED"; // VOW CHECK — purple
  if (line.includes("STEP 2")) return "#D97706"; // PATTERN   — amber
  if (line.includes("STEP 3")) return "#2563EB"; // SCORE     — blue
  if (line.includes("STEP 4")) return "#DC2626"; // NUDGE     — red
  if (line.includes("STEP 5")) return "#0891B2"; // LANGUAGE  — cyan
  if (line.includes("STEP 6")) return "#059669"; // STRESS    — green
  if (line.includes("STEP 7")) return "#6B6860"; // SEBI      — grey
  return "#6B6860";
}

function isStepLine(line: string) {
  return /STEP \d/.test(line);
}

const EVIDENCE_LABELS: Record<NonNullable<StepKind>, string> = {
  vow:     "EVIDENCE · VOWS VIOLATED",
  pattern: "EVIDENCE · PATTERN DETAIL",
  score:   "EVIDENCE · SCORE BREAKDOWN",
  nudge:   "EVIDENCE · COMMITMENT PHRASE",
  lang:    "EVIDENCE · LOCAL-LANGUAGE TRANSLATION",
  stress:  "EVIDENCE · SESSION STRESS",
  sebi:    "EVIDENCE · SEBI RAG SOURCE",
};

function EvidencePanel(props: {
  kind: NonNullable<StepKind>;
  color: string;
  analysis: BehavioralAnalysis;
}) {
  const { kind, color, analysis } = props;
  const monoStyle: React.CSSProperties = {
    fontFamily: "'DM Mono', 'Courier New', monospace",
    fontSize: "11px",
    color: "#1A1814",
    lineHeight: "1.7",
    margin: 0,
  };

  return (
    <div style={{
      margin: "4px 0 8px 28px",
      padding: "10px 12px",
      borderRadius: "6px",
      background: "#ffffff",
      border: `1px dashed ${color}55`,
      borderLeft: `3px solid ${color}`,
    }}>
      <div style={{
        fontSize: "9px", fontWeight: "700", color, letterSpacing: "0.07em",
        marginBottom: "6px",
      }}>
        {EVIDENCE_LABELS[kind]}
      </div>

      {kind === "vow" && (
        analysis.vows_violated.length === 0 ? (
          <p style={monoStyle}>No vows violated this session.</p>
        ) : (
          <ul style={{ ...monoStyle, paddingLeft: "16px", margin: 0 }}>
            {analysis.vows_violated.map((v, i) => (
              <li key={i} style={{ marginBottom: "2px" }}>
                <span style={{ color: "#DC2626" }}>•</span> "{v}"
              </li>
            ))}
          </ul>
        )
      )}

      {kind === "pattern" && (
        <div style={monoStyle}>
          <div>
            <span style={{ color: "#9B9890" }}>pattern</span>{" → "}
            <strong style={{ color }}>{analysis.detected_pattern}</strong>
          </div>
          <div>
            <span style={{ color: "#9B9890" }}>risk</span>{" → "}
            <strong style={{ color }}>{analysis.risk_level.toUpperCase()}</strong>
          </div>
        </div>
      )}

      {kind === "score" && (
        <div style={monoStyle}>
          <div>
            <span style={{ color: "#9B9890" }}>raw score</span>{" → "}
            <strong style={{ color }}>{analysis.behavioral_score}</strong>
            <span style={{ color: "#9B9890" }}> / 1000</span>
          </div>
          <div>
            <span style={{ color: "#9B9890" }}>threshold for Speed Bump</span>{" → 600"}
          </div>
          <div>
            <span style={{ color: "#9B9890" }}>diff</span>{" → "}
            <strong style={{ color: analysis.behavioral_score > 600 ? "#DC2626" : "#16A34A" }}>
              {analysis.behavioral_score > 600 ? "+" : ""}
              {analysis.behavioral_score - 600}
            </strong>
          </div>
        </div>
      )}

      {kind === "nudge" && (
        analysis.nudge_message ? (
          <p style={{ ...monoStyle, fontStyle: "italic" }}>
            "{analysis.nudge_message}"
          </p>
        ) : (
          <p style={monoStyle}>No nudge — score below 600.</p>
        )
      )}

      {kind === "lang" && (
        analysis.nudge_message_local ? (
          <p style={{ ...monoStyle, fontStyle: "italic" }}>
            "{analysis.nudge_message_local}"
          </p>
        ) : (
          <p style={monoStyle}>No translation produced.</p>
        )
      )}

      {kind === "stress" && (
        <div style={monoStyle}>
          <div>
            <span style={{ color: "#9B9890" }}>stress score</span>{" → "}
            <strong style={{ color }}>{analysis.crisis_score}</strong>
            <span style={{ color: "#9B9890" }}> / 100</span>
          </div>
          <div>
            <span style={{ color: "#9B9890" }}>monitoring threshold</span>{" → 70"}
          </div>
          <div>
            <span style={{ color: "#9B9890" }}>stress flag</span>{" → "}
            <strong style={{ color: analysis.crisis_detected ? "#DC2626" : "#16A34A" }}>
              {analysis.crisis_detected ? "elevated" : "below threshold"}
            </strong>
          </div>
        </div>
      )}

      {kind === "sebi" && (
        analysis.sebi_disclosure ? (
          <div>
            <p style={{ ...monoStyle, marginBottom: "6px" }}>
              "{analysis.sebi_disclosure}"
            </p>
            {analysis.sebi_source && (
              <div style={{ fontSize: "10px", color: "#9B9890" }}>
                Retrieved from <strong style={{ color }}>{analysis.sebi_source}</strong> via ChromaDB RAG
              </div>
            )}
          </div>
        ) : (
          <p style={monoStyle}>No SEBI grounding retrieved this run.</p>
        )
      )}
    </div>
  );
}

export function ThinkingLog({
  log, inferenceTime, streamingText, streaming, streamStatus, analysis,
}: Props) {
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const bodyRef = useRef<HTMLDivElement>(null);

  function toggleStep(idx: number) {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx); else next.add(idx);
      return next;
    });
  }

  // Reset expanded state when a new analysis lands.
  useEffect(() => { setExpanded(new Set()); }, [analysis?.thinking_log]);

  // Auto-open while streaming so the user actually sees the live tokens.
  useEffect(() => {
    if (streaming) setOpen(true);
  }, [streaming]);

  // Source of truth: live stream takes precedence; otherwise final log.
  const displayText = (streaming || streamingText) ? (streamingText ?? "") : (log ?? "");

  // Auto-scroll the body to follow the cursor while streaming.
  useEffect(() => {
    if (streaming && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [displayText, streaming]);

  if (!displayText && !streaming) return null;

  const lines = displayText.split("\n").filter(l => l.trim());
  const stepCount = lines.filter(isStepLine).length;

  return (
    <div style={{
      background: "#ffffff",
      borderRadius: "12px",
      border: "1px solid #E8E5DF",
      overflow: "hidden",
    }}>
      {/* ── Toggle header ────────────────────────────────────────────────── */}
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          gap: "10px",
          padding: "12px 16px",
          border: "none",
          background: open ? "#FFF7ED" : "transparent",
          cursor: "pointer",
          textAlign: "left",
          transition: "background 0.15s",
          borderBottom: open ? "1px solid #FED7AA" : "none",
        }}
      >
        {/* Brain icon */}
        <div style={{
          width: "28px", height: "28px", borderRadius: "7px", flexShrink: 0,
          background: "#FFF7ED", border: "1px solid #FED7AA",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
            stroke="#F97316" strokeWidth="2.5" strokeLinecap="round">
            <path d="M9.5 2a2.5 2.5 0 0 1 5 0v1a2.5 2.5 0 0 1-5 0V2z"/>
            <path d="M4 14a8 8 0 0 1 16 0"/>
            <path d="M12 3v11"/>
            <path d="M8 17h8"/>
            <path d="M6 21h12"/>
          </svg>
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: "11px", fontWeight: "700", color: "#1A1814",
            textTransform: "uppercase", letterSpacing: "0.07em",
            display: "flex", alignItems: "center", gap: "6px",
          }}>
            Fin AI Audit Trace
            {streaming && (
              <span style={{
                fontSize: "9px", fontWeight: "700",
                color: "#16A34A", background: "#F0FDF4",
                border: "1px solid #BBF7D0",
                borderRadius: "99px", padding: "1px 6px",
                display: "inline-flex", alignItems: "center", gap: "4px",
              }}>
                <span style={{
                  width: "5px", height: "5px", borderRadius: "50%",
                  background: "#16A34A",
                  animation: "tl-pulse 1s infinite",
                }}/>
                LIVE
              </span>
            )}
          </div>
          <div style={{ fontSize: "10px", color: "#9B9890", marginTop: "1px" }}>
            {streaming
              ? (streamStatus || "Streaming Fin AI audit trace…")
              : `${stepCount} audit steps · local Fin AI · data stays private${
                  inferenceTime ? ` · ${inferenceTime.toFixed(1)}s` : ""
                }`}
          </div>
        </div>

        {/* Step count badge */}
        <span style={{
          fontSize: "10px", fontWeight: "700",
          color: "#F97316", background: "#FFF7ED",
          border: "1px solid #FED7AA",
          borderRadius: "99px", padding: "2px 8px", flexShrink: 0,
        }}>
          {streaming && stepCount === 0 ? "…" : `${stepCount} steps`}
        </span>

        {/* Chevron */}
        <svg
          width="14" height="14" viewBox="0 0 24 24" fill="none"
          stroke="#9B9890" strokeWidth="2.5" strokeLinecap="round"
          style={{ flexShrink: 0, transform: open ? "rotate(90deg)" : "none", transition: "transform 0.2s" }}
        >
          <polyline points="9 18 15 12 9 6"/>
        </svg>
      </button>

      {/* ── Log body ─────────────────────────────────────────────────────── */}
      {open && (
        <div ref={bodyRef} style={{
          maxHeight: "280px",
          overflowY: "auto",
          padding: "12px 16px",
          display: "flex",
          flexDirection: "column",
          gap: "6px",
          scrollBehavior: "smooth",
        }}>
          <style>{`
            @keyframes tl-pulse  { 0%,100% {opacity:1} 50% {opacity:0.4} }
            @keyframes tl-cursor { 0%,49% {opacity:1} 50%,100% {opacity:0} }
          `}</style>

          {lines.length === 0 && streaming && (
            <p style={{
              fontSize: "12px", color: "#9B9890",
              fontFamily: "'DM Mono', 'Courier New', monospace",
              padding: "8px 10px",
            }}>
              {streamStatus || "Connecting to Fin AI…"}<span style={{
                animation: "tl-cursor 1s infinite", color: "#F97316", fontWeight: "700",
              }}>█</span>
            </p>
          )}

          {lines.map((line, i) => {
            const isStep    = isStepLine(line);
            const color     = stepColor(line);
            const isLastLine = i === lines.length - 1;
            const kind       = stepKind(line);
            const clickable  = isStep && kind !== null && !!analysis && !streaming;
            const isOpen     = expanded.has(i);

            return (
              <div key={i}>
                <div
                  onClick={() => clickable && toggleStep(i)}
                  role={clickable ? "button" : undefined}
                  tabIndex={clickable ? 0 : undefined}
                  onKeyDown={e => {
                    if (clickable && (e.key === "Enter" || e.key === " ")) {
                      e.preventDefault();
                      toggleStep(i);
                    }
                  }}
                  style={{
                    display: "flex",
                    gap: "10px",
                    alignItems: "flex-start",
                    padding: isStep ? "6px 10px" : "2px 10px",
                    borderRadius: isStep ? "6px" : "0",
                    background: isStep ? `${color}10` : "transparent",
                    borderLeft: isStep ? `3px solid ${color}` : "3px solid transparent",
                    cursor: clickable ? "pointer" : "default",
                    transition: "background 0.15s",
                  }}
                  onMouseEnter={e => {
                    if (clickable) e.currentTarget.style.background = `${color}1A`;
                  }}
                  onMouseLeave={e => {
                    if (clickable) e.currentTarget.style.background = `${color}10`;
                  }}
                >
                  {/* Line number */}
                  <span style={{
                    fontSize: "10px",
                    fontFamily: "'DM Mono', 'Courier New', monospace",
                    color: isStep ? color : "#C8C5BE",
                    flexShrink: 0,
                    marginTop: "1px",
                    minWidth: "18px",
                    fontWeight: isStep ? "700" : "400",
                  }}>
                    {String(i + 1).padStart(2, "0")}
                  </span>

                  {/* Line text */}
                  <p style={{
                    flex: 1,
                    fontSize: "12px",
                    fontFamily: "'DM Mono', 'Courier New', monospace",
                    color: isStep ? color : "#6B6860",
                    lineHeight: "1.6",
                    fontWeight: isStep ? "600" : "400",
                    wordBreak: "break-word",
                  }}>
                    {line}
                    {streaming && isLastLine && (
                      <span style={{
                        display: "inline-block",
                        width: "0.55em",
                        marginLeft: "2px",
                        color: "#F97316",
                        fontWeight: "700",
                        animation: "tl-cursor 1s infinite",
                      }}>█</span>
                    )}
                  </p>

                  {/* Evidence chevron (only on clickable rows) */}
                  {clickable && (
                    <svg
                      width="12" height="12" viewBox="0 0 24 24" fill="none"
                      stroke={color} strokeWidth="2.5" strokeLinecap="round"
                      style={{
                        flexShrink: 0, marginTop: "4px",
                        transform: isOpen ? "rotate(90deg)" : "none",
                        transition: "transform 0.2s",
                        opacity: 0.7,
                      }}
                    >
                      <polyline points="9 18 15 12 9 6"/>
                    </svg>
                  )}
                </div>

                {/* Inline evidence panel */}
                {clickable && isOpen && (
                  <EvidencePanel kind={kind!} color={color} analysis={analysis!} />
                )}
              </div>
            );
          })}

          {/* Run history — persistent across reloads, append-only */}
          <PersistentRunHistory />

          {/* Footer note */}
          <div style={{
            marginTop: "8px",
            paddingTop: "10px",
            borderTop: "1px solid #E8E5DF",
            textAlign: "center",
          }}>
            <p style={{ fontSize: "11px", color: "#9B9890" }}>
              🔒 This audit trace was assembled on your device — no cloud, no surveillance
            </p>
          </div>
        </div>
      )}
    </div>
  );
}


// ── Persistent run history ───────────────────────────────────────────────────
// Reads from the global thinkingLog store. Survives component unmount, page
// reload, mode switches — anything short of an explicit clear. Groups entries
// by runId so the user can scroll back through every analysis the Fin AI has ever
// produced for this account.

function PersistentRunHistory() {
  const { entries, clear } = useThinkingLog();
  const [open, setOpen] = useState(false);

  const runs = useMemo(() => {
    const byRun = new Map<string, typeof entries>();
    for (const e of entries) {
      const key = e.runId || "_unscoped";
      if (!byRun.has(key)) byRun.set(key, []);
      byRun.get(key)!.push(e);
    }
    // Newest run first
    return Array.from(byRun.entries()).reverse();
  }, [entries]);

  if (runs.length <= 1) return null;   // nothing useful to show yet

  return (
    <div style={{ marginTop: "12px", paddingTop: "10px", borderTop: "1px solid #E8E5DF" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <button
          onClick={() => setOpen(v => !v)}
          style={{
            background: "none", border: "none", padding: 0, cursor: "pointer",
            fontSize: "11px", fontWeight: 700, color: "#6B6860",
            letterSpacing: "0.04em",
          }}
        >
          {open ? "▾" : "▸"}  PREVIOUS RUNS · {runs.length}
        </button>
        {open && (
          <button
            onClick={() => { if (confirm("Clear all stored audit logs?")) clear(); }}
            style={{
              background: "none", border: "none", padding: 0, cursor: "pointer",
              fontSize: "10px", color: "#DC2626", fontWeight: 700,
            }}
          >Clear history</button>
        )}
      </div>

      {open && (
        <div style={{
          marginTop: 8, maxHeight: 280, overflowY: "auto",
          background: "#FAFAF8", border: "1px solid #E8E5DF", borderRadius: 8,
          padding: "8px 10px", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          fontSize: 11, color: "#3F3D38", lineHeight: 1.5,
        }}>
          {runs.map(([runId, runEntries]) => {
            const head = runEntries[0];
            return (
              <details key={runId} style={{ marginBottom: 6 }}>
                <summary style={{ cursor: "pointer", fontWeight: 700, color: "#1A1814" }}>
                  {new Date(head.ts).toLocaleTimeString()} · {head.mode?.toUpperCase()} ·
                  {" "}{runEntries.length} events
                </summary>
                {runEntries.map(e => (
                  <div key={e.id} style={{
                    paddingLeft: 12,
                    color: e.kind === "error"  ? "#DC2626"
                        : e.kind === "result" ? "#15803D"
                        : e.kind === "status" ? "#6B6860"
                        : "#3F3D38",
                  }}>
                    {e.kind === "token" ? e.text : `[${e.kind}] ${e.text}`}
                  </div>
                ))}
              </details>
            );
          })}
        </div>
      )}
    </div>
  );
}
