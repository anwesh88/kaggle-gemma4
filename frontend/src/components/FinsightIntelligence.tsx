"use client";
import type { BehavioralAnalysis } from "@/types";

interface Props {
  analysis: BehavioralAnalysis | null;
  loading: boolean;
  model?: string;     // raw model id from /health
  /** When false, the analysis pipeline is intentionally idle (e.g. Paper
   *  mode with zero trades). Render an empty-state instead of the
   *  loading skeleton so the user knows nothing is being analyzed. */
  enabled?: boolean;
  /** Mode-aware empty-state copy (set by Dashboard from the active theme). */
  emptyTitle?: string;
  emptyBody?: string;
  emptyAccent?: string;
}

// Keep the user-facing label generic even when the backend exposes a raw id.
function formatModel(_raw: string | undefined): string {
  return "AI model";
}

const RISK = {
  low:    { color: "#16A34A", bg: "#F0FDF4", border: "#BBF7D0", label: "LOW RISK"    },
  medium: { color: "#D97706", bg: "#FFFBEB", border: "#FDE68A", label: "MEDIUM RISK" },
  high:   { color: "#DC2626", bg: "#FEF2F2", border: "#FECACA", label: "HIGH RISK"   },
};

const PATTERN_ICON: Record<string, string> = {
  "Revenge Trading":  "↩",
  "FOMO":             "⚡",
  "Over-Leveraging":  "⚠",
  "Addiction Loop":   "∞",
  "Panic Selling":    "↓",
  "Healthy Trading":  "✓",
};

// Skeleton shimmer block
function Shimmer({ w = "100%", h = 12 }: { w?: string; h?: number }) {
  return (
    <div style={{
      width: w, height: `${h}px`, borderRadius: "6px",
      background: "linear-gradient(90deg, #F5F4F0 25%, #ECEAE4 50%, #F5F4F0 75%)",
      backgroundSize: "200% 100%",
      animation: "shimmer 1.4s infinite",
    }} />
  );
}

export function FinsightIntelligence({
  analysis, loading, model,
  enabled = true,
  emptyTitle  = "Awaiting your first trade",
  emptyBody   = "The AI starts analyzing once you place a trade. Your dashboard will populate from there.",
  emptyAccent = "#2563EB",
}: Props) {
  const r     = analysis ? RISK[analysis.risk_level] : RISK.low;
  const score = analysis?.behavioral_score ?? 0;
  const pct   = (score / 1000) * 100;
  const modelLabel = formatModel(model);
  const inferS = analysis?.inference_seconds ?? null;
  const isRealInference = inferS !== null && inferS > 0;

  // Header shared
  const header = (
    <div style={{
      padding: "11px 16px",
      borderBottom: "1px solid #E8E5DF",
      display: "flex", alignItems: "center", gap: "8px",
    }}>
      {/* Orange shield icon */}
      <div style={{
        width: "28px", height: "28px", borderRadius: "7px",
        background: "#FFF7ED", border: "1px solid #FED7AA",
        display: "flex", alignItems: "center", justifyContent: "center",
        flexShrink: 0,
      }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
          stroke="#F97316" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
        </svg>
      </div>

      <span style={{
        fontSize: "11px", fontWeight: "700", color: "#1A1814",
        textTransform: "uppercase", letterSpacing: "0.07em",
      }}>
        Finsight Intelligence
      </span>

      {loading && (
        <span style={{
          marginLeft: "auto", fontSize: "10px", color: "#F97316",
          fontWeight: "600", display: "flex", alignItems: "center", gap: "4px",
        }}>
          <span style={{
            width: "6px", height: "6px", borderRadius: "50%",
            background: "#F97316", display: "inline-block",
            animation: "pulse 1s infinite",
          }} />
          Analyzing...
        </span>
      )}

      {!loading && (
        <span
          title={
            isRealInference
              ? `Real AI model inference, CPU-local, ${inferS!.toFixed(2)}s`
              : "AI model inference unavailable or still pending"
          }
          style={{
            marginLeft: "auto", display: "flex", alignItems: "center", gap: "5px",
            fontSize: "10px", fontWeight: "600",
            color: isRealInference ? "#16A34A" : "#9B9890",
            background: isRealInference ? "#F0FDF4" : "#F9F8F6",
            border: `1px solid ${isRealInference ? "#BBF7D0" : "#E8E5DF"}`,
            borderRadius: "99px", padding: "2px 8px",
            fontVariantNumeric: "tabular-nums",
          }}>
          {/* Tiny CPU/chip icon — communicates "this ran on your machine" */}
          <svg width="9" height="9" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="4" y="4" width="16" height="16" rx="2"/>
            <rect x="9" y="9" width="6" height="6"/>
            <line x1="9"  y1="2"  x2="9"  y2="4"/>
            <line x1="15" y1="2"  x2="15" y2="4"/>
            <line x1="9"  y1="20" x2="9"  y2="22"/>
            <line x1="15" y1="20" x2="15" y2="22"/>
            <line x1="20" y1="9"  x2="22" y2="9"/>
            <line x1="20" y1="14" x2="22" y2="14"/>
            <line x1="2"  y1="9"  x2="4"  y2="9"/>
            <line x1="2"  y1="14" x2="4"  y2="14"/>
          </svg>
          <span>
            {modelLabel}
            {inferS !== null && (
              <>
                <span style={{ opacity: 0.6, margin: "0 4px" }}>·</span>
                {inferS.toFixed(1)}s
              </>
            )}
            <span style={{ opacity: 0.6, margin: "0 4px" }}>·</span>
            local
          </span>
        </span>
      )}
    </div>
  );

  // ── Disabled / empty state — Paper mode with no trades ─────────────────
  if (!enabled && !analysis) {
    return (
      <div style={{
        background: "#fff", borderRadius: "12px",
        border: "1px solid #E8E5DF", overflow: "hidden",
      }}>
        {header}
        <div style={{ padding: "28px 20px", textAlign: "center" }}>
          <div style={{
            width: "44px", height: "44px", borderRadius: "10px",
            background: `${emptyAccent}15`, border: `1px solid ${emptyAccent}40`,
            margin: "0 auto 12px",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
              stroke={emptyAccent} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8"  x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
          </div>
          <div style={{
            fontSize: "14px", fontWeight: "800", color: "#1A1814",
            marginBottom: "6px",
          }}>
            {emptyTitle}
          </div>
          <p style={{
            fontSize: "12px", color: "#6B6860", lineHeight: "1.6",
            maxWidth: "260px", margin: "0 auto",
          }}>
            {emptyBody}
          </p>
        </div>
      </div>
    );
  }

  // ── Loading skeleton ────────────────────────────────────────────────────
  if (!analysis) {
    return (
      <div style={{
        background: "#fff", borderRadius: "12px",
        border: "1px solid #E8E5DF", overflow: "hidden",
      }}>
        <style>{`
          @keyframes shimmer {
            0%   { background-position: 200% 0; }
            100% { background-position: -200% 0; }
          }
          @keyframes pulse {
            0%, 100% { opacity: 1; }
            50%       { opacity: 0.4; }
          }
        `}</style>
        {header}
        <div style={{ padding: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
            <div style={{ padding: "14px", borderRadius: "10px", background: "#F9F8F6",
              border: "1px solid #E8E5DF", display: "flex", flexDirection: "column", gap: "8px" }}>
              <Shimmer w="60%" h={28} />
              <Shimmer w="80%" h={10} />
            </div>
            <div style={{ padding: "14px", borderRadius: "10px", background: "#F9F8F6",
              border: "1px solid #E8E5DF", display: "flex", flexDirection: "column", gap: "8px" }}>
              <Shimmer w="50%" h={18} />
              <Shimmer w="70%" h={10} />
            </div>
          </div>
          <Shimmer h={6} />
          <Shimmer h={52} />
          <Shimmer h={64} />
        </div>
      </div>
    );
  }

  if (analysis.inference_seconds === null && analysis.detected_pattern.toLowerCase().includes("unavailable")) {
    return (
      <div style={{
        background: "#fff", borderRadius: "12px",
        border: "1px solid #E8E5DF", overflow: "hidden",
      }}>
        {header}
        <div style={{ padding: "20px 16px" }}>
          <div style={{
            padding: "13px", borderRadius: "10px",
            background: "#FFFBEB", border: "1px solid #FDE68A",
          }}>
            <div style={{
              fontSize: "11px", fontWeight: "800", color: "#B45309",
              textTransform: "uppercase", letterSpacing: "0.06em",
              marginBottom: "6px",
            }}>
              AI model inference unavailable
            </div>
            <p style={{ fontSize: "12px", color: "#7C5E10", lineHeight: "1.6" }}>
              No behavioral score or pattern is being shown because the AI model did not complete this run.
              The thinking log preserves the trade context that was prepared for the model.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // ── Full analysis view ──────────────────────────────────────────────────
  return (
    <div style={{
      background: "#fff", borderRadius: "12px",
      border: "1px solid #E8E5DF", overflow: "hidden",
    }}>
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.4; }
        }
        @keyframes barGrow {
          from { width: 0%; }
          to   { width: ${pct}%; }
        }
      `}</style>

      {header}

      <div style={{ padding: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>

        {/* Score + Risk grid */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
          {/* Score tile */}
          <div style={{
            padding: "14px 12px", borderRadius: "10px",
            background: "#F9F8F6", border: "1px solid #E8E5DF",
            textAlign: "center",
          }}>
            <div style={{
              fontSize: "30px", fontWeight: "800", lineHeight: 1,
              color: r.color,
              fontVariantNumeric: "tabular-nums",
            }}>
              {score}
            </div>
            <div style={{
              fontSize: "10px", fontWeight: "600", color: "#9B9890",
              textTransform: "uppercase", letterSpacing: "0.05em", marginTop: "5px",
            }}>
              Behavioral Score
            </div>
            <div style={{ fontSize: "10px", color: "#9B9890", marginTop: "2px" }}>/ 1000</div>
          </div>

          {/* Risk tile */}
          <div style={{
            padding: "14px 12px", borderRadius: "10px",
            background: r.bg, border: `1px solid ${r.border}`,
            textAlign: "center",
            display: "flex", flexDirection: "column",
            alignItems: "center", justifyContent: "center", gap: "6px",
          }}>
            {/* Pulsing dot */}
            <div style={{
              width: "10px", height: "10px", borderRadius: "50%",
              background: r.color,
              boxShadow: `0 0 0 3px ${r.bg}, 0 0 0 5px ${r.color}40`,
              animation: analysis.risk_level === "high" ? "pulse 1.5s infinite" : "none",
            }} />
            <div style={{ fontSize: "14px", fontWeight: "800", color: r.color }}>
              {analysis.risk_level.toUpperCase()}
            </div>
            <div style={{
              fontSize: "10px", fontWeight: "600", color: r.color,
              opacity: 0.7, textTransform: "uppercase", letterSpacing: "0.05em",
            }}>
              Risk Level
            </div>
          </div>
        </div>

        {/* Score bar */}
        <div>
          <div style={{
            display: "flex", justifyContent: "space-between",
            fontSize: "11px", color: "#9B9890", marginBottom: "5px",
          }}>
            <span>Risk Score</span>
            <span style={{ fontWeight: "700", color: r.color }}>{score} / 1000</span>
          </div>
          <div style={{
            height: "6px", background: "#F5F4F0",
            borderRadius: "4px", overflow: "hidden",
          }}>
            <div style={{
              height: "100%", borderRadius: "4px",
              background: analysis.risk_level === "high"
                ? "linear-gradient(90deg, #F97316, #DC2626)"
                : analysis.risk_level === "medium"
                  ? "#D97706"
                  : "#16A34A",
              width: `${pct}%`,
              transition: "width 0.8s cubic-bezier(0.4,0,0.2,1)",
            }} />
          </div>
        </div>

        {/* Pattern detected */}
        {analysis.detected_pattern && (
          <div style={{
            padding: "11px 13px", borderRadius: "10px",
            background: "#F9F8F6", border: "1px solid #E8E5DF",
          }}>
            <div style={{
              fontSize: "10px", fontWeight: "700", color: "#9B9890",
              textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "7px",
            }}>
              Pattern Detected
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "9px" }}>
              <div style={{
                width: "30px", height: "30px", borderRadius: "8px",
                background: r.bg, border: `1px solid ${r.border}`,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: "15px", color: r.color, flexShrink: 0,
              }}>
                {PATTERN_ICON[analysis.detected_pattern] ?? "⚠"}
              </div>
              <span style={{ fontSize: "14px", fontWeight: "700", color: "#1A1814" }}>
                {analysis.detected_pattern}
              </span>
            </div>
          </div>
        )}

        {/* Nudge message (EN + local language) */}
        {analysis.nudge_message && (
          <div style={{
            padding: "11px 13px", borderRadius: "10px",
            background: "#FEF2F2", border: "1px solid #FECACA",
          }}>
            <div style={{
              fontSize: "10px", fontWeight: "700", color: "#DC2626",
              textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "6px",
            }}>
              Commitment Phrase
            </div>
            <p className="behavioral-message" style={{ 
              fontSize: "13px", 
              fontStyle: "italic", 
              lineHeight: "1.6",
              color: "#991B1B",
            }}>
              "{analysis.nudge_message}"
            </p>
            {analysis.nudge_message_local && (
              <p className="behavioral-message" style={{
                fontSize: "12px", 
                color: "#B91C1C",
                marginTop: "6px", 
                lineHeight: "1.6", 
                opacity: 0.85,
                borderTop: "1px solid #FECACA", 
                paddingTop: "6px",
              }}>
                {analysis.nudge_message_local}
              </p>
            )}
          </div>
        )}

        {/* Vows violated */}
        {analysis.vows_violated && analysis.vows_violated.length > 0 && (
          <div style={{
            padding: "10px 13px", borderRadius: "10px",
            background: "#FFF7ED", border: "1px solid #FED7AA",
          }}>
            <div style={{
              fontSize: "10px", fontWeight: "700", color: "#C2410C",
              textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "5px",
            }}>
              Vow Violated
            </div>
            {analysis.vows_violated.map((v, i) => (
              <p key={i} style={{ fontSize: "12px", color: "#92400E", lineHeight: "1.5" }}>
                • {v}
              </p>
            ))}
          </div>
        )}

        {/* SEBI disclosure */}
        {analysis.sebi_disclosure && (
          <div style={{
            padding: "10px 13px", borderRadius: "10px",
            background: "#F9F8F6", border: "1px solid #E8E5DF",
          }}>
            <div style={{
              fontSize: "10px", fontWeight: "700", color: "#9B9890",
              textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "4px",
            }}>
              SEBI · {analysis.sebi_source ?? "Guidelines"}
            </div>
            <p style={{ fontSize: "11px", color: "#6B6860", lineHeight: "1.6" }}>
              {analysis.sebi_disclosure}
            </p>
          </div>
        )}

        {/* Edge AI badge */}
        <div style={{
          padding: "9px 12px", borderRadius: "8px", textAlign: "center",
          background: "#FFF7ED", border: "1px solid #FED7AA",
        }}>
          <p style={{ fontSize: "11px", fontWeight: "700", color: "#C2410C" }}>
            🔒 Privacy-First Edge AI
          </p>
          <p style={{ fontSize: "10px", color: "#92400E", marginTop: "3px",
            lineHeight: "1.5", opacity: 0.8 }}>
            All analysis runs locally · Zero data sent to any server
          </p>
          <p style={{ fontSize: "9px", color: "#92400E", marginTop: "5px",
            lineHeight: "1.45", opacity: 0.7 }}>
            AI model inference runs locally through Ollama.
          </p>
        </div>

      </div>
    </div>
  );
}
