"use client";
import { useEffect, useState } from "react";
import { useMode } from "@/contexts/ModeContext";
import type { Mode } from "@/lib/mode";
import { api } from "@/lib/api";

interface KiteAvailability {
  configured: boolean;            // KITE_API_KEY present in backend .env
  authenticated: boolean;         // user has a live access_token
  user_name?: string;
  session_source?: string | null;
  expected_redirect_url?: string;
  warning?: string | null;
  error?: string;
}

const CARD_COLORS: Record<Mode, { bg: string; border: string; accent: string; pill: string; pillBg: string }> = {
  demo:  { bg: "#FFF7ED", border: "#FED7AA", accent: "#F97316", pill: "#C2410C", pillBg: "#FFEDD5" },
  paper: { bg: "#EFF6FF", border: "#BFDBFE", accent: "#2563EB", pill: "#1E40AF", pillBg: "#DBEAFE" },
  kite:  { bg: "#F0FDF4", border: "#BBF7D0", accent: "#16A34A", pill: "#15803D", pillBg: "#DCFCE7" },
};

export function ModeSelector() {
  const { setMode } = useMode();
  const [kite, setKite] = useState<KiteAvailability | null>(null);
  const [loading, setLoading] = useState(false);
  const [showPaste, setShowPaste] = useState(false);
  const [pasteValue, setPasteValue] = useState("");
  const [pasteErr, setPasteErr] = useState<string | null>(null);
  const [pasting, setPasting] = useState(false);

  // Probe whether the backend has Kite Connect configured.
  useEffect(() => {
    api.kiteStatus()
      .then(s => setKite(s))
      .catch(() => setKite({ configured: false, authenticated: false }));
  }, []);

  function pickMode(m: Mode) {
    if (m === "kite" && !kite?.configured) return;
    setMode(m);
  }

  async function startKiteLogin() {
    if (loading) return;
    setLoading(true);
    try {
      const { login_url } = await api.kiteLoginUrl();
      window.location.href = login_url;
    } catch (e) {
      console.error("kite login failed:", e);
      setLoading(false);
    }
  }

  async function submitPaste() {
    if (pasting || !pasteValue.trim()) return;
    setPasting(true);
    setPasteErr(null);
    try {
      const r = await api.kiteManualCallback(pasteValue.trim());
      const fresh = await api.kiteStatus();
      setKite(fresh);
      setShowPaste(false);
      setPasteValue("");
      setMode("kite");
      console.log(`[kite] manual login OK as ${r.user_name}`);
    } catch (e: any) {
      setPasteErr(e?.message || "Could not exchange that token. Make sure you copied it from a fresh login.");
    } finally {
      setPasting(false);
    }
  }

  return (
    <div style={{
      minHeight: "100vh",
      background: "linear-gradient(180deg, #FFFBF5 0%, #F5F4F0 60%, #FFF7ED 100%)",
      display: "flex", alignItems: "center", justifyContent: "center",
      padding: "32px 16px",
      fontFamily: "'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif",
    }}>
      <div style={{ maxWidth: "980px", width: "100%" }}>

        {/* Brand */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "center",
          gap: "14px", marginBottom: "32px",
        }}>
          <div style={{
            width: "48px", height: "48px", borderRadius: "12px",
            background: "#F97316",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
              stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
          </div>
          <div>
            <div style={{ fontSize: "22px", fontWeight: "800", letterSpacing: "-0.01em", color: "#1A1814" }}>
              Finsight OS
            </div>
            <div style={{ fontSize: "12px", color: "#9B9890", letterSpacing: "0.04em" }}>
              BEHAVIORAL GUARDIAN · BUILT ON AI MODEL
            </div>
          </div>
        </div>

        {/* Headline */}
        <div style={{ textAlign: "center", marginBottom: "28px" }}>
          <h1 style={{
            fontSize: "32px", fontWeight: "800", color: "#1A1814",
            letterSpacing: "-0.02em", margin: "0 0 10px",
          }}>
            How would you like to explore?
          </h1>
          <p style={{ fontSize: "15px", color: "#6B6860", lineHeight: "1.6", maxWidth: "640px", margin: "0 auto" }}>
            Three deployment modes ship with Finsight OS. Pick whichever
            matches your situation. You can change it later from the dashboard.
          </p>
        </div>

        {/* Cards */}
        <div style={{
          display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
          gap: "16px", marginBottom: "20px",
        }}>

          {/* DEMO CARD */}
          <ModeCard
            mode="demo"
            badge="INSTANT"
            title="Demo Mode"
            description="Pre-loaded high-risk session, zero setup. Best for a quick tour or showing a friend in 30 seconds."
            features={[
              "5 closed losing trades + 2 open positions",
              "Speed Bump fires on first analysis",
              "All AI model features active",
              "Zero broker credentials needed",
            ]}
            cta="Enter Demo"
            onClick={() => pickMode("demo")}
            disabled={false}
          />

          {/* PAPER CARD */}
          <ModeCard
            mode="paper"
            badge="FREE PRACTICE"
            title="Paper Trading"
            description="Place real trades against live Yahoo prices. Trades persist to a local SQLite engine with FIFO P&L matching. No broker account required."
            features={[
              "Real NSE prices via Yahoo Finance",
              "FIFO lot matching · realized P&L",
              "₹100,000 paper capital",
              "Trades flow into AI model analysis",
            ]}
            cta="Start Paper Trading"
            onClick={() => pickMode("paper")}
            disabled={false}
          />

          {/* KITE CARD */}
          <ModeCard
            mode="kite"
            badge={kite?.configured ? "REAL BROKER" : "REQUIRES SETUP"}
            title="Live Kite Connect"
            description={
              kite?.configured
                ? "Connect your actual Zerodha account. Free-tier of Kite Connect (₹0/month) supported. You retain full control — Finsight only reads and adds the Speed Bump layer."
                : "Configure KITE_API_KEY in backend/.env. Kite Connect Personal tier is free (₹0). See docs/kite-setup.md for the 5-minute walkthrough."
            }
            features={
              kite?.configured
                ? [
                    "OAuth login via Zerodha",
                    "Real holdings, positions, P&L",
                    "Daily access-token refresh",
                    "Rate-limited at 3 req/s per Kite TOS",
                  ]
                : [
                    "kite.trade/connect → register app",
                    "Set redirect URL · localhost:8000",
                    "Add api_key + secret to .env",
                    "Restart backend → mode unlocks",
                  ]
            }
            cta={
              !kite?.configured ? "Backend not configured" :
              kite.authenticated ? `Continue as ${kite.user_name || "trader"}` :
              loading ? "Redirecting…" :
              "Login with Zerodha"
            }
            onClick={
              !kite?.configured ? () => {} :
              kite.authenticated ? () => pickMode("kite") :
              startKiteLogin
            }
            disabled={!kite?.configured || loading}
          />
        </div>

        {kite?.configured && kite.warning && (
          <div style={{
            marginTop: "6px",
            padding: "12px 14px",
            background: "#FFFBEB",
            border: "1px solid #FDE68A",
            borderRadius: "12px",
            fontSize: "12px",
            color: "#92400E",
            lineHeight: 1.55,
          }}>
            <div style={{ fontWeight: 700, marginBottom: "4px" }}>
              Live Kite setup note
            </div>
            <div>{kite.warning}</div>
            {kite.expected_redirect_url && (
              <div style={{ marginTop: "4px" }}>
                Register this redirect URL exactly: <code>{kite.expected_redirect_url}</code>
              </div>
            )}
          </div>
        )}

        {/* Recovery-only manual paste fallback */}
        {kite?.configured && !kite.authenticated && (
          <div style={{
            marginTop: "8px",
            padding: "14px 16px",
            background: "#FFFBEB",
            border: "1px solid #FDE68A",
            borderRadius: "12px",
            fontSize: "12px",
            color: "#7C5E10",
          }}>
            <button
              onClick={() => setShowPaste(v => !v)}
              style={{
                background: "none", border: "none", padding: 0, cursor: "pointer",
                color: "#92400E", fontWeight: 700, fontSize: "12px",
                letterSpacing: "0.02em",
              }}
            >
              {showPaste ? "▾  Hide recovery login" : "▸  Redirect misconfigured? Use recovery login"}
            </button>
            {showPaste && (
              <div style={{ marginTop: "10px", display: "flex", flexDirection: "column", gap: "8px" }}>
                <p style={{ margin: 0, lineHeight: 1.55 }}>
                  Browser login is expected to return through the backend callback. If your Kite app
                  is still registered to the wrong redirect host and you landed on a dead page, copy
                  the full URL from the address bar and paste it below. We&apos;ll extract the
                  <code> request_token </code> and finish the login server-side.
                </p>
                <textarea
                  value={pasteValue}
                  onChange={e => setPasteValue(e.target.value)}
                  placeholder="Paste the full URL or just the request_token…"
                  rows={2}
                  style={{
                    width: "100%", padding: "8px 10px",
                    border: "1px solid #FCD34D", borderRadius: "8px",
                    fontSize: "12px", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                    color: "#1A1814", background: "#FFFFFF",
                    resize: "vertical",
                  }}
                />
                <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                  <button
                    onClick={submitPaste}
                    disabled={pasting || !pasteValue.trim()}
                    style={{
                      background: "#16A34A", color: "#fff",
                      border: "none", borderRadius: "8px",
                      padding: "8px 14px", fontWeight: 700, fontSize: "12px",
                      cursor: pasting ? "wait" : "pointer",
                      opacity: pasting || !pasteValue.trim() ? 0.6 : 1,
                    }}
                  >
                    {pasting ? "Exchanging…" : "Finish login"}
                  </button>
                  <a
                    href="https://developers.kite.trade/apps/"
                    target="_blank" rel="noreferrer"
                    style={{ fontSize: "11px", color: "#92400E" }}
                  >
                    Or fix the redirect URL in your Kite app →
                  </a>
                </div>
                {pasteErr && (
                  <div style={{ color: "#B91C1C", fontSize: "12px" }}>
                    {pasteErr}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Footer attribution */}
        <div style={{
          textAlign: "center", fontSize: "11px", color: "#9B9890",
          letterSpacing: "0.03em", marginTop: "20px",
        }}>
          <div>Edge-AI · 100% local inference via AI model + Ollama · Open source · MIT licensed</div>
          <div style={{ marginTop: "5px", letterSpacing: 0 }}>
            AI model inference runs locally through Ollama.
          </div>
        </div>
      </div>
    </div>
  );
}


// ────────────────────────────────────────────────────────────────────────────

interface CardProps {
  mode: Mode;
  badge: string;
  title: string;
  description: string;
  features: string[];
  cta: string;
  onClick: () => void;
  disabled: boolean;
}

function ModeCard({ mode, badge, title, description, features, cta, onClick, disabled }: CardProps) {
  const c = CARD_COLORS[mode];

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        textAlign: "left",
        background: "#ffffff",
        border: `1.5px solid ${c.border}`,
        borderRadius: "16px",
        padding: "22px 22px 18px",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.6 : 1,
        boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
        transition: "transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease",
        font: "inherit",
        color: "#1A1814",
        display: "flex", flexDirection: "column", gap: "12px",
      }}
      onMouseEnter={e => {
        if (disabled) return;
        e.currentTarget.style.transform = "translateY(-3px)";
        e.currentTarget.style.boxShadow = `0 8px 24px ${c.accent}22, 0 1px 3px rgba(0,0,0,0.04)`;
        e.currentTarget.style.borderColor = c.accent;
      }}
      onMouseLeave={e => {
        e.currentTarget.style.transform = "none";
        e.currentTarget.style.boxShadow = "0 1px 3px rgba(0,0,0,0.04)";
        e.currentTarget.style.borderColor = c.border;
      }}
    >
      {/* Badge */}
      <span style={{
        alignSelf: "flex-start",
        fontSize: "10px", fontWeight: "700",
        color: c.pill, background: c.pillBg,
        border: `1px solid ${c.border}`,
        borderRadius: "99px", padding: "3px 9px",
        letterSpacing: "0.07em",
      }}>
        {badge}
      </span>

      {/* Title */}
      <h2 style={{
        fontSize: "20px", fontWeight: "800", margin: 0,
        letterSpacing: "-0.01em",
      }}>
        {title}
      </h2>

      {/* Description */}
      <p style={{ fontSize: "13px", color: "#6B6860", lineHeight: "1.55", margin: 0 }}>
        {description}
      </p>

      {/* Feature list */}
      <ul style={{ margin: "4px 0 0", padding: 0, listStyle: "none",
                   display: "flex", flexDirection: "column", gap: "5px" }}>
        {features.map((f, i) => (
          <li key={i} style={{
            display: "flex", alignItems: "flex-start", gap: "7px",
            fontSize: "12px", color: "#1A1814",
          }}>
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none"
              stroke={c.accent} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"
              style={{ flexShrink: 0, marginTop: "4px" }}>
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            <span>{f}</span>
          </li>
        ))}
      </ul>

      {/* CTA */}
      <div style={{
        marginTop: "8px", paddingTop: "12px",
        borderTop: `1px solid ${c.border}`,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        fontSize: "13px", fontWeight: "700", color: c.accent,
      }}>
        <span>{cta}</span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
          stroke={c.accent} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <line x1="5" y1="12" x2="19" y2="12"/>
          <polyline points="12 5 19 12 12 19"/>
        </svg>
      </div>
    </button>
  );
}
