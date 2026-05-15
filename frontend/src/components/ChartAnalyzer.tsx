"use client";
import { useState, useRef } from "react";
import { api } from "@/lib/api";

type ChartResult = Awaited<ReturnType<typeof api.analyzeChart>>;

interface Props {
  // Headline behavioral warning — emits the personalized_insight so the
  // dashboard can also show the one-liner next to the FinsightIntelligence card.
  onInsight: (insight: string) => void;
}

export function ChartAnalyzer({ onInsight }: Props) {
  const [analyzing, setAnalyzing] = useState(false);
  const [result,    setResult]    = useState<ChartResult | null>(null);
  const [dragging,  setDragging]  = useState(false);
  const [fileName,  setFileName]  = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    setFileName(file.name);
    setAnalyzing(true);
    setResult(null);
    try {
      const r = await api.analyzeChart(file);
      setResult(r);
      onInsight(r.personalized_insight || r.insight || "");
    } catch {
      const stub: ChartResult = {
        insight: "Chart analysis unavailable — AI model vision requires Ollama to be running.",
        market_state: "unknown",
        market_structure: { trend: "unknown", momentum: "unknown", volatility: "unknown",
          volume_confirmation: "unknown", key_observation: "Chart could not be analyzed." },
        behavioral_risk: { fomo_probability: 0, revenge_probability: 0, panic_probability: 0,
          overconfidence_risk: 0, emotional_risk_level: "unknown", primary_concern: "—" },
        decision_quality: { score: 0, rating: "unknown", entry_timing: "—",
          risk_reward: "—", stop_placement: "—", position_sizing: "—" },
        personalized_insight: "Chart analysis unavailable.",
        behavioral_warning:   "Chart analysis unavailable.",
      };
      setResult(stub);
      onInsight(stub.personalized_insight);
    } finally {
      setAnalyzing(false);
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith("image/")) handleFile(file);
  }

  return (
    <div style={{
      background: "#ffffff", borderRadius: "12px",
      border: "1px solid #E8E5DF", overflow: "hidden",
    }}>
      {/* Header */}
      <div style={{
        padding: "11px 16px", borderBottom: "1px solid #E8E5DF",
        display: "flex", alignItems: "center", gap: "8px",
      }}>
        <div style={{
          width: "28px", height: "28px", borderRadius: "7px", flexShrink: 0,
          background: "#EFF6FF", border: "1px solid #BFDBFE",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
            stroke="#2563EB" strokeWidth="2.5" strokeLinecap="round">
            <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"/>
            <circle cx="12" cy="12" r="3"/>
          </svg>
        </div>
        <span style={{
          fontSize: "11px", fontWeight: "700", color: "#1A1814",
          textTransform: "uppercase", letterSpacing: "0.07em",
        }}>
          Chart Analyzer · Behavioral Intelligence
        </span>
        <span style={{
          marginLeft: "auto", fontSize: "10px", color: "#9B9890",
          background: "#F9F8F6", border: "1px solid #E8E5DF",
          borderRadius: "99px", padding: "2px 7px",
        }}>
          AI model vision · local
        </span>
      </div>

      <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: "12px" }}>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          style={{ display: "none" }}
          onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])}
        />

        <div
          onClick={() => !analyzing && inputRef.current?.click()}
          onDragOver={e => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          style={{
            padding: "20px 16px", borderRadius: "10px",
            border: `2px dashed ${dragging ? "#2563EB" : analyzing ? "#FED7AA" : "#D0CCC4"}`,
            background: dragging ? "#EFF6FF" : analyzing ? "#FFF7ED" : "#F9F8F6",
            cursor: analyzing ? "not-allowed" : "pointer",
            display: "flex", flexDirection: "column",
            alignItems: "center", justifyContent: "center",
            gap: "8px", textAlign: "center",
            transition: "all 0.2s ease",
          }}
        >
          {analyzing ? (
            <>
              <div style={{
                width: "28px", height: "28px", borderRadius: "50%",
                border: "3px solid #FED7AA",
                borderTopColor: "#F97316",
                animation: "spin 0.8s linear infinite",
              }} />
              <p style={{ fontSize: "12px", fontWeight: "600", color: "#C2410C" }}>
                AI model analyzing chart + your behavior history…
              </p>
              {fileName && <p style={{ fontSize: "11px", color: "#9B9890" }}>{fileName}</p>}
            </>
          ) : (
            <>
              <div style={{
                width: "36px", height: "36px", borderRadius: "10px",
                background: "#EFF6FF", border: "1px solid #BFDBFE",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                  stroke="#2563EB" strokeWidth="2.5" strokeLinecap="round">
                  <polyline points="16 16 12 12 8 16"/>
                  <line x1="12" y1="12" x2="12" y2="21"/>
                  <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/>
                </svg>
              </div>
              <div>
                <p style={{ fontSize: "12px", fontWeight: "600", color: "#2563EB" }}>
                  Upload chart screenshot
                </p>
                <p style={{ fontSize: "11px", color: "#9B9890", marginTop: "2px" }}>
                  Click or drag & drop · PNG, JPG supported
                </p>
              </div>
            </>
          )}
        </div>

        {result && !analyzing && <FourLayerOutput r={result} fileName={fileName} />}
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(4px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}


// ── 4-layer output ──────────────────────────────────────────────────────────

function FourLayerOutput({ r, fileName }: { r: ChartResult; fileName: string | null }) {
  const ms  = r.market_state || "unknown";
  const br  = r.behavioral_risk;
  const dq  = r.decision_quality;
  const struct = r.market_structure;

  // Headline color reflects the worst signal across emotional_risk and decision_quality
  const isHigh =
    br?.emotional_risk_level === "high" ||
    dq?.rating === "poor" ||
    Math.max(br?.fomo_probability ?? 0, br?.revenge_probability ?? 0,
             br?.panic_probability ?? 0, br?.overconfidence_risk ?? 0) >= 70;
  const headlineColor = isHigh ? "#DC2626" : br?.emotional_risk_level === "medium" ? "#D97706" : "#16A34A";
  const headlineBg    = isHigh ? "#FEF2F2" : br?.emotional_risk_level === "medium" ? "#FFFBEB" : "#F0FDF4";
  const headlineBorder= isHigh ? "#FECACA" : br?.emotional_risk_level === "medium" ? "#FDE68A" : "#BBF7D0";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, animation: "fadeIn 0.3s ease" }}>

      {/* Headline behavioral warning */}
      <div style={{
        padding: "12px 14px", borderRadius: 10,
        background: headlineBg, border: `1px solid ${headlineBorder}`,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
          <span style={{ fontSize: 10, fontWeight: 700, color: headlineColor,
            textTransform: "uppercase", letterSpacing: "0.07em" }}>
            Behavioral Decision Intelligence
          </span>
          <RiskPill level={br?.emotional_risk_level || "unknown"} />
        </div>
        <p style={{ fontSize: 13, fontWeight: 700, color: "#1A1814", lineHeight: 1.5, margin: 0 }}>
          {r.personalized_insight || r.behavioral_warning}
        </p>
        {r.behavioral_warning && r.behavioral_warning !== r.personalized_insight && (
          <p style={{ fontSize: 12, color: "#6B6860", lineHeight: 1.5, marginTop: 6 }}>
            {r.behavioral_warning}
          </p>
        )}
      </div>

      {/* Market structure */}
      <Section title="Market Structure" accent="#2563EB">
        <Grid>
          <KV k="State"      v={cap(ms)} />
          <KV k="Trend"      v={cap(struct?.trend)} />
          <KV k="Momentum"   v={cap(struct?.momentum)} />
          <KV k="Volatility" v={cap(struct?.volatility)} />
          <KV k="Volume"     v={cap(struct?.volume_confirmation)} />
        </Grid>
        {struct?.key_observation && (
          <p style={{ fontSize: 12, color: "#374151", marginTop: 8, lineHeight: 1.55 }}>
            <b>What I see:</b> {struct.key_observation}
          </p>
        )}
      </Section>

      {/* Behavioral risk scores — each bar carries an inline reason when 0% */}
      <Section title="Behavioral Risk" accent="#DC2626">
        <Bar label="FOMO entry"           pct={br?.fomo_probability    ?? 0} reason={br?.reasons?.fomo_probability} />
        <Bar label="Revenge trading"      pct={br?.revenge_probability ?? 0} reason={br?.reasons?.revenge_probability} />
        <Bar label="Panic / capitulation" pct={br?.panic_probability   ?? 0} reason={br?.reasons?.panic_probability} />
        <Bar label="Overconfidence"       pct={br?.overconfidence_risk ?? 0} reason={br?.reasons?.overconfidence_risk} />
        {br?.primary_concern && br.primary_concern !== "—" && (
          <p style={{ fontSize: 12, color: "#7F1D1D", marginTop: 6 }}>
            <b>Primary concern:</b> {br.primary_concern}
          </p>
        )}
        {/* All-zero banner — surfaces ONE actionable explanation when every
            risk dimension came back 0. Helps users understand the bars
            aren't broken; the AI literally found no behavioral risk. */}
        {(() => {
          const all0 =
            (br?.fomo_probability ?? 0) === 0 &&
            (br?.revenge_probability ?? 0) === 0 &&
            (br?.panic_probability ?? 0) === 0 &&
            (br?.overconfidence_risk ?? 0) === 0;
          if (!all0) return null;
          return (
            <div style={{
              marginTop: 10, padding: "8px 10px",
              background: "#F0FDF4", border: "1px solid #BBF7D0",
              borderRadius: 8, fontSize: 12, color: "#166534", lineHeight: 1.55,
            }}>
              <b>No active risk signals.</b>{" "}
              This chart shows no breakout, crash, or recovery setup that would
              indicate emotional trading — and your behavioral history hasn't logged
              enough sessions yet to flag personalized patterns. The bars will fill in
              as you build a trade history and as charts with stronger directional
              moves are analyzed.
            </div>
          );
        })()}
      </Section>

      {/* Decision quality */}
      <Section title={`Decision Quality · ${dq?.score ?? 0} / 100`} accent="#0F766E">
        <Grid>
          <KV k="Rating"      v={cap(dq?.rating)} highlight={ratingColor(dq?.rating)} />
          <KV k="Entry"       v={cap(dq?.entry_timing)} />
          <KV k="Risk/Reward" v={cap(dq?.risk_reward)} />
          <KV k="Sizing"      v={cap(dq?.position_sizing)} />
        </Grid>
        {dq?.stop_placement && dq.stop_placement !== "—" && (
          <p style={{ fontSize: 12, color: "#374151", marginTop: 8, lineHeight: 1.55 }}>
            <b>Stop placement:</b> {dq.stop_placement}
          </p>
        )}
      </Section>

      {r.error && (
        <p style={{ fontSize: 11, color: "#9CA3AF", fontStyle: "italic" }}>
          Note: {r.error}
        </p>
      )}
      {fileName && (
        <p style={{ fontSize: 10, color: "#9CA3AF" }}>
          Source: {fileName}
        </p>
      )}
    </div>
  );
}


// ── Small building blocks ──────────────────────────────────────────────────

function Section({ title, accent, children }: { title: string; accent: string; children: React.ReactNode }) {
  return (
    <div style={{
      padding: "12px 14px", borderRadius: 10,
      background: "#fff", border: `1px solid ${accent}22`,
    }}>
      <div style={{
        fontSize: 11, fontWeight: 700, color: accent,
        textTransform: "uppercase", letterSpacing: "0.06em",
        marginBottom: 8,
      }}>{title}</div>
      {children}
    </div>
  );
}

function Grid({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
      gap: 8,
    }}>{children}</div>
  );
}

function KV({ k, v, highlight }: { k: string; v: string; highlight?: string }) {
  return (
    <div>
      <div style={{ fontSize: 10, color: "#6B6860", textTransform: "uppercase", letterSpacing: "0.04em" }}>
        {k}
      </div>
      <div style={{
        fontSize: 13, fontWeight: 700, marginTop: 2,
        color: highlight || "#1A1814",
      }}>
        {v}
      </div>
    </div>
  );
}

function Bar({ label, pct, reason }: { label: string; pct: number; reason?: string }) {
  const clamped = Math.max(0, Math.min(100, pct));
  const color = clamped >= 70 ? "#DC2626" : clamped >= 40 ? "#D97706" : "#16A34A";
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between",
        fontSize: 11, color: "#1A1814", marginBottom: 3 }}>
        <span>{label}</span>
        <b style={{ color }}>{clamped}%</b>
      </div>
      <div style={{ height: 6, background: "#F1EEE7", borderRadius: 99, overflow: "hidden" }}>
        <div style={{
          width: `${clamped}%`, height: "100%", background: color,
          transition: "width 0.5s ease",
        }} />
      </div>
      {clamped === 0 && reason && (
        <div style={{
          fontSize: 11, color: "#6B6860", marginTop: 4, fontStyle: "italic",
          lineHeight: 1.45,
        }}>
          {reason}
        </div>
      )}
    </div>
  );
}

function RiskPill({ level }: { level: string }) {
  const map: Record<string, { bg: string; color: string; border: string }> = {
    low:    { bg: "#F0FDF4", color: "#15803D", border: "#BBF7D0" },
    medium: { bg: "#FFFBEB", color: "#B45309", border: "#FDE68A" },
    high:   { bg: "#FEF2F2", color: "#B91C1C", border: "#FECACA" },
  };
  const c = map[level] || { bg: "#F1F5F9", color: "#475569", border: "#CBD5E1" };
  return (
    <span style={{
      marginLeft: "auto", fontSize: 10, fontWeight: 800,
      color: c.color, background: c.bg, border: `1px solid ${c.border}`,
      borderRadius: 99, padding: "2px 8px", textTransform: "uppercase", letterSpacing: "0.04em",
    }}>
      {level} emotional risk
    </span>
  );
}

function cap(s: string | undefined | null): string {
  if (!s) return "—";
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function ratingColor(r: string | undefined | null): string {
  if (r === "good")    return "#15803D";
  if (r === "average") return "#B45309";
  if (r === "poor")    return "#B91C1C";
  return "#1A1814";
}
