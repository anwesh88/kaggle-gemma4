"use client";
import { useEffect, useRef, useState } from "react";
import type { BehavioralAnalysis } from "@/types";
import { api } from "@/lib/api";
import { useMode } from "@/contexts/ModeContext";
import { themeFor } from "@/lib/modeTheme";

/**
 * Map a behavioral score + detected pattern to a Speed Bump cooldown.
 *
 * The "Mindful Speed Bump" idea is that more dangerous patterns require
 * more cognitive friction. Revenge Trading at score 892 is a 12-second
 * cooldown; Addiction Loop near 1000 deserves more; light FOMO needs less.
 *
 * Range: 6s (low edge of high-risk) to 18s (worst case). The exact-match
 * commitment phrase + this clock both gate the Confirm button.
 */
function computeCooldown(analysis: BehavioralAnalysis | null): number {
  if (!analysis || analysis.risk_level !== "high") return 0;
  const score = analysis.behavioral_score;
  // Score ramp: 600 → 6s, 800 → 10s, 950 → 14s
  let s = Math.max(6, Math.min(14, Math.round(6 + (score - 600) * 0.023)));
  // Pattern multiplier: addiction loop is the worst, healthy / panic less so
  switch (analysis.detected_pattern) {
    case "Addiction Loop":   s = Math.min(18, Math.round(s * 1.4)); break;
    case "Revenge Trading":  s = Math.min(18, Math.round(s * 1.15)); break;
    case "Over-Leveraging":  s = Math.min(18, Math.round(s * 1.1));  break;
    case "FOMO":             s = Math.max(6,  Math.round(s * 0.95)); break;
    default: break;
  }
  return s;
}

// Default suggestions shown when the user hasn't built a watchlist yet
// (and for Demo / Paper modes which don't use the Kite stock search).
const DEFAULT_INSTRUMENTS = [
  { symbol: "RELIANCE",              price: 1298.40 },
  { symbol: "INFY",                  price: 1847.60 },
  { symbol: "TCS",                   price: 4102.50 },
  { symbol: "HDFCBANK",              price: 1782.90 },
  { symbol: "NIFTY24DEC23000CE",     price: 187.50  },
  { symbol: "BANKNIFTY24DEC49000PE", price: 224.30  },
];

// localStorage key shared with StockSearch.tsx — keeps the two components
// in sync without needing a context or prop drill.
const WATCHLIST_STORAGE_KEY = "finsight.kite.watchlist.v1";

function readKiteWatchlist(): { symbol: string }[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(WATCHLIST_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed)
      ? parsed.map((s: any) => ({ symbol: String(s.tradingsymbol || "") })).filter(s => s.symbol)
      : [];
  } catch {
    return [];
  }
}

interface Props {
  analysis: BehavioralAnalysis | null;
  onTradeExecuted?: () => void;
}

export function TradePanel({ analysis, onTradeExecuted }: Props) {
  const { mode } = useMode();
  const theme    = themeFor(mode);

  const [symbol,   setSymbol]   = useState(DEFAULT_INSTRUMENTS[0].symbol);
  const [quantity, setQuantity] = useState(10);
  const [price,    setPrice]    = useState(DEFAULT_INSTRUMENTS[0].price);
  const [action,   setAction]   = useState<"BUY" | "SELL">("BUY");

  // Watchlist-aware suggestions: in Kite mode, prefer the user's saved
  // watchlist (set via StockSearch above). Falls back to DEFAULT_INSTRUMENTS
  // when the watchlist is empty or in non-Kite modes. Re-reads on every
  // mount + on window focus so adding a stock in StockSearch refreshes here.
  const [watchlistSyms, setWatchlistSyms] = useState<{ symbol: string }[]>(() => readKiteWatchlist());
  useEffect(() => {
    if (mode !== "kite") return;
    const refresh = () => setWatchlistSyms(readKiteWatchlist());
    refresh();
    window.addEventListener("focus", refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener("focus", refresh);
      window.removeEventListener("storage", refresh);
    };
  }, [mode]);
  const instrumentOptions = mode === "kite" && watchlistSyms.length > 0
    ? watchlistSyms
    : DEFAULT_INSTRUMENTS;

  // Speed Bump state
  const [showBump,    setShowBump]    = useState(false);
  const [typed,       setTyped]       = useState("");
  const [loading,     setLoading]     = useState(false);
  const [done,        setDone]        = useState(false);
  // Live Kite second-stage confirmation modal (Q3=3.C: high-risk only)
  const [showLiveConfirm, setShowLiveConfirm] = useState(false);

  // Cooldown state — counts down from cooldownTotal in 100ms ticks.
  const cooldownTotal = computeCooldown(analysis);
  const [cooldownMs, setCooldownMs] = useState(0);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const isHigh   = analysis?.risk_level === "high";
  const required = analysis?.nudge_message ?? "";
  const matches  = required.length > 0 &&
    typed.trim().toLowerCase() === required.trim().toLowerCase();
  const cooldownDone = cooldownMs <= 0;
  const canConfirm   = matches && cooldownDone && !loading;

  // When the modal opens, kick off the cooldown clock.
  useEffect(() => {
    if (!showBump) {
      if (tickRef.current) { clearInterval(tickRef.current); tickRef.current = null; }
      return;
    }
    const totalMs = cooldownTotal * 1000;
    setCooldownMs(totalMs);
    const id = setInterval(() => {
      setCooldownMs(prev => {
        const next = prev - 100;
        if (next <= 0) {
          if (tickRef.current) { clearInterval(tickRef.current); tickRef.current = null; }
          return 0;
        }
        return next;
      });
    }, 100);
    tickRef.current = id;
    return () => {
      clearInterval(id);
      if (tickRef.current === id) tickRef.current = null;
    };
  }, [showBump, cooldownTotal]);

  function handleSymbolChange(sym: string) {
    setSymbol(sym);
    // Look up a default price across both the user's watchlist and the
    // legacy DEFAULT_INSTRUMENTS table. If the symbol came from the user's
    // free-form input (custom symbol not in either list), keep the current
    // price — they'll type a fresh one in the Price field.
    const known = DEFAULT_INSTRUMENTS.find(i => i.symbol === sym);
    if (known) setPrice((known as any).price);
    setDone(false);
    setTyped("");
    setShowBump(false);
  }

  function handleQtyChange(val: number) {
    setQuantity(Math.max(1, Math.floor(val) || 1));
  }

  function handlePriceChange(val: number) {
    setPrice(Math.max(0.05, Number(val.toFixed(2)) || 0.05));
  }

  function handleTradeClick(type: "BUY" | "SELL") {
    setAction(type);
    // Q3=3.C — Live Kite mode: low-risk trades skip the Speed Bump entirely
    // (matches normal broker UX). High-risk trades fire Speed Bump THEN
    // a second "Place LIVE Order on Zerodha" confirmation.
    if (isHigh) {
      setTyped("");
      setShowBump(true);
    } else {
      executeTrade(type);
    }
  }

  async function executeTrade(type: "BUY" | "SELL") {
    setLoading(true);
    try {
      await api.confirmTrade(symbol, quantity, price, type);
      setDone(true);
      onTradeExecuted?.();
      setTimeout(() => setDone(false), 3000);
    } catch (e) {
      console.error("Trade failed:", e);
    } finally {
      setLoading(false);
    }
  }

  async function handleCommit() {
    if (!canConfirm) return;
    setShowBump(false);
    setTyped("");
    // Q3=3.C: in Live Kite mode AND high-risk trade, show one more confirm
    // before sending to broker. Otherwise execute directly.
    if (mode === "kite") {
      setShowLiveConfirm(true);
      return;
    }
    await executeTrade(action);
  }

  async function handleLiveConfirm() {
    setShowLiveConfirm(false);
    await executeTrade(action);
  }

  const orderValue = (quantity * price).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  // ── Shared input style ─────────────────────────────────────────────────
  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "9px 11px",
    border: "1px solid #D0CCC4",
    borderRadius: "8px",
    background: "#F9F8F6",
    color: "#1A1814",
    fontSize: "13px",
    outline: "none",
    transition: "border-color 0.15s",
  };

  const labelStyle: React.CSSProperties = {
    display: "block",
    fontSize: "10px",
    fontWeight: "700",
    color: "#9B9890",
    textTransform: "uppercase",
    letterSpacing: "0.06em",
    marginBottom: "5px",
    fontFamily: "var(--font-sans)",
  };

  return (
    <>
      {/* ── Speed Bump overlay ──────────────────────────────────────────── */}
      {showBump && (
        <div style={{
          position: "fixed", inset: 0, zIndex: 50,
          background: "rgba(26,24,20,0.45)",
          backdropFilter: "blur(4px)",
          display: "flex", alignItems: "center", justifyContent: "center",
          padding: "16px",
          animation: "fadeIn 0.2s ease",
        }}>
          <div style={{
            background: "#ffffff",
            borderRadius: "16px",
            padding: "28px 26px",
            maxWidth: "440px",
            width: "100%",
            border: "1px solid #FECACA",
            boxShadow: "0 24px 64px rgba(220,38,38,0.12), 0 4px 16px rgba(0,0,0,0.08)",
          }}>
            {/* Icon with cooldown ring */}
            <div style={{ textAlign: "center", marginBottom: "18px" }}>
              {(() => {
                const SIZE = 64, R = 28, CIRC = 2 * Math.PI * R;
                const totalMs = cooldownTotal * 1000;
                const progress = totalMs > 0 ? cooldownMs / totalMs : 0;  // 1 → 0
                const offset   = CIRC * (1 - progress);                   // depletes
                const ringColor = cooldownDone ? "#16A34A" : "#DC2626";

                return (
                  <div style={{
                    position: "relative", width: `${SIZE}px`, height: `${SIZE}px`,
                    margin: "0 auto 14px",
                  }}>
                    {/* Cooldown progress ring */}
                    <svg width={SIZE} height={SIZE} style={{
                      position: "absolute", inset: 0, transform: "rotate(-90deg)",
                    }}>
                      <circle cx={SIZE/2} cy={SIZE/2} r={R}
                        fill="none" stroke="#FECACA" strokeWidth="3"/>
                      <circle cx={SIZE/2} cy={SIZE/2} r={R}
                        fill="none" stroke={ringColor} strokeWidth="3"
                        strokeLinecap="round"
                        strokeDasharray={CIRC}
                        strokeDashoffset={offset}
                        style={{ transition: "stroke-dashoffset 0.1s linear, stroke 0.3s" }}
                      />
                    </svg>
                    {/* Inner circle with warning icon OR countdown number */}
                    <div style={{
                      position: "absolute", inset: "8px",
                      borderRadius: "50%",
                      background: "#FEF2F2",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      border: "1.5px solid #FECACA",
                    }}>
                      {cooldownDone ? (
                        <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
                          stroke="#DC2626" strokeWidth="2.5" strokeLinecap="round">
                          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                          <line x1="12" y1="9" x2="12" y2="13"/>
                          <line x1="12" y1="17" x2="12.01" y2="17"/>
                        </svg>
                      ) : (
                        <span style={{
                          fontSize: "16px", fontWeight: "800", color: "#DC2626",
                          fontVariantNumeric: "tabular-nums",
                        }}>
                          {Math.ceil(cooldownMs / 1000)}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })()}

              <h3 style={{
                fontSize: "18px", fontWeight: "800", color: "#1A1814",
                marginBottom: "6px", letterSpacing: "-0.01em",
              }}>
                {theme.bumpHeadline}
              </h3>
              <p style={{ fontSize: "13px", color: "#6B6860", lineHeight: "1.6" }}>
                AI model detected{" "}
                <strong style={{ color: "#DC2626" }}>{analysis?.detected_pattern}</strong>
                {" "}— behavioral score{" "}
                <strong style={{ color: "#DC2626" }}>{analysis?.behavioral_score}/1000</strong>.
                {cooldownDone
                  ? " Type your commitment to continue."
                  : ` Reflect for ${cooldownTotal} seconds, then type your commitment.`}
              </p>
            </div>

            {/* Phrase box */}
            <div style={{
              background: "#FEF2F2", border: "1px solid #FECACA",
              borderRadius: "10px", padding: "12px 16px", marginBottom: "14px",
            }}>
              <p style={{
                fontSize: "10px", fontWeight: "700", color: "#DC2626",
                textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "6px",
              }}>
                Type this exactly:
              </p>
              <p className="behavioral-message" style={{
                fontSize: "14px",
                fontStyle: "italic", lineHeight: "1.6",
                color: "#991B1B",
              }}>
                "{required}"
              </p>
            </div>

            {/* Input */}
            <input
              value={typed}
              onChange={e => setTyped(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleCommit()}
              placeholder="Type the commitment phrase above..."
              autoFocus
              style={{
                ...inputStyle,
                marginBottom: "10px",
                border: `1.5px solid ${matches ? "#16A34A" : typed.length > 0 ? "#F97316" : "#D0CCC4"}`,
                background: matches ? "#F0FDF4" : "#ffffff",
                fontFamily: "'DM Mono', 'Courier New', monospace",
                fontSize: "13px",
              }}
            />

            {/* Progress bar */}
            {typed.length > 0 && (
              <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "14px" }}>
                <div style={{
                  flex: 1, height: "3px", background: "#E8E5DF",
                  borderRadius: "2px", overflow: "hidden",
                }}>
                  <div style={{
                    height: "100%", borderRadius: "2px",
                    background: matches ? "#16A34A" : "#F97316",
                    width: `${Math.min(100, (typed.length / required.length) * 100)}%`,
                    transition: "width 0.1s, background 0.3s",
                  }} />
                </div>
                <span style={{
                  fontSize: "11px", fontWeight: "600",
                  color: matches ? "#16A34A" : "#9B9890",
                  minWidth: "48px", textAlign: "right",
                }}>
                  {matches ? "✓ Match" : `${typed.length}/${required.length}`}
                </span>
              </div>
            )}

            {/* Action buttons */}
            <div style={{ display: "flex", gap: "10px" }}>
              <button
                onClick={() => { setShowBump(false); setTyped(""); }}
                style={{
                  flex: 1, padding: "11px", borderRadius: "8px",
                  border: "1px solid #D0CCC4", background: "transparent",
                  color: "#6B6860", fontSize: "13px", cursor: "pointer",
                  fontWeight: "500",
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleCommit}
                disabled={!canConfirm}
                style={{
                  flex: 2, padding: "11px", borderRadius: "8px",
                  border: "none", fontSize: "13px", fontWeight: "700",
                  cursor: canConfirm ? "pointer" : "not-allowed",
                  background: canConfirm ? "#DC2626" : "#E8E5DF",
                  color: canConfirm ? "#ffffff" : "#9B9890",
                  transition: "all 0.2s",
                }}
              >
                {loading
                  ? "Placing order..."
                  : !cooldownDone
                    ? `Reflect · ${Math.ceil(cooldownMs / 1000)}s`
                    : !matches
                      ? "Complete phrase to unlock"
                      : (action === "BUY" ? theme.confirmBuy : theme.confirmSell)}
              </button>
            </div>

            <p style={{
              textAlign: "center", fontSize: "11px",
              color: "#9B9890", marginTop: "12px",
            }}>
              This pause is for your protection · Finsight OS
            </p>
          </div>
        </div>
      )}

      {/* ── Live Kite second-stage confirmation (Q3=3.C, high-risk only) ─ */}
      {showLiveConfirm && (
        <div style={{
          position: "fixed", inset: 0, zIndex: 60,
          background: "rgba(26,24,20,0.55)",
          backdropFilter: "blur(4px)",
          display: "flex", alignItems: "center", justifyContent: "center",
          padding: "16px",
        }}>
          <div style={{
            background: "#ffffff",
            borderRadius: "16px",
            padding: "26px 24px",
            maxWidth: "420px",
            width: "100%",
            border: "2px solid #16A34A",
            boxShadow: "0 24px 64px rgba(22,163,74,0.2), 0 4px 16px rgba(0,0,0,0.1)",
          }}>
            <div style={{
              display: "flex", alignItems: "center", gap: "10px",
              marginBottom: "12px",
            }}>
              <div style={{
                width: "32px", height: "32px", borderRadius: "50%",
                background: "#F0FDF4", border: "2px solid #16A34A",
                display: "flex", alignItems: "center", justifyContent: "center",
                flexShrink: 0,
              }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                  stroke="#16A34A" strokeWidth="3" strokeLinecap="round">
                  <circle cx="12" cy="12" r="10"/>
                  <polyline points="12 6 12 12 16 14"/>
                </svg>
              </div>
              <div style={{
                fontSize: "10px", fontWeight: "800", color: "#15803D",
                letterSpacing: "0.07em",
              }}>
                FINAL CONFIRMATION · LIVE ZERODHA
              </div>
            </div>

            <h3 style={{
              fontSize: "17px", fontWeight: "800", color: "#1A1814",
              letterSpacing: "-0.01em", marginBottom: "10px",
            }}>
              Place a REAL order for ₹{(quantity * price).toLocaleString("en-IN", {
                minimumFractionDigits: 2, maximumFractionDigits: 2
              })}?
            </h3>
            <p style={{ fontSize: "13px", color: "#6B6860", lineHeight: "1.6", marginBottom: "8px" }}>
              <strong style={{ color: "#1A1814" }}>{action} {quantity}× {symbol}</strong> at ₹{price.toFixed(2)}
              will be submitted to your Zerodha account via the Kite Connect API.
            </p>
            <p style={{ fontSize: "12px", color: "#9B9890", lineHeight: "1.5", marginBottom: "16px" }}>
              You've cleared the Speed Bump. This is the final safety check before
              the order moves real money.
            </p>

            <div style={{ display: "flex", gap: "10px" }}>
              <button
                onClick={() => setShowLiveConfirm(false)}
                style={{
                  flex: 1, padding: "11px", borderRadius: "8px",
                  border: "1px solid #D0CCC4", background: "transparent",
                  color: "#6B6860", fontSize: "13px", cursor: "pointer",
                  fontWeight: "600", fontFamily: "inherit",
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleLiveConfirm}
                style={{
                  flex: 2, padding: "11px", borderRadius: "8px",
                  border: "none", background: "#16A34A", color: "#ffffff",
                  fontSize: "13px", fontWeight: "700", cursor: "pointer",
                  fontFamily: "inherit",
                }}
              >
                ✓ Place LIVE Order
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Trade card ──────────────────────────────────────────────────── */}
      <div style={{
        background: "#ffffff", borderRadius: "12px",
        border: "1px solid #E8E5DF", overflow: "hidden",
      }}>
        {/* Header */}
        <div style={{
          padding: "11px 16px", borderBottom: "1px solid #E8E5DF",
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <span style={{
            fontSize: "11px", fontWeight: "700", color: "#1A1814",
            textTransform: "uppercase", letterSpacing: "0.07em",
          }}>
            Place Order
          </span>

          {isHigh && (
            <span style={{
              fontSize: "11px", fontWeight: "600", color: "#DC2626",
              background: "#FEF2F2", border: "1px solid #FECACA",
              borderRadius: "99px", padding: "2px 9px",
            }}>
              ⚠ High Risk — commitment required
            </span>
          )}
        </div>

        <div style={{ padding: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
          {/* Instrument selector — hybrid: pick from watchlist OR type any symbol */}
          <div>
            <label style={labelStyle}>Instrument</label>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                type="text"
                value={symbol}
                onChange={e => handleSymbolChange(e.target.value.toUpperCase().trim())}
                placeholder="Type or pick a symbol"
                list="finsight-instrument-options"
                style={{ ...inputStyle, flex: 1, textTransform: "uppercase" }}
              />
              <datalist id="finsight-instrument-options">
                {instrumentOptions.map(i => (
                  <option key={i.symbol} value={i.symbol} />
                ))}
              </datalist>
            </div>
            {mode === "kite" && watchlistSyms.length === 0 && (
              <div style={{ fontSize: 11, color: "#6B6860", marginTop: 4 }}>
                Tip: search a stock in the Search & Trade panel above to add it to your watchlist —
                it'll auto-suggest here.
              </div>
            )}
          </div>

          {/* Qty + Price row */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
            <div>
              <label style={labelStyle}>Quantity</label>
              <input
                type="number"
                min="1"
                step="1"
                value={quantity}
                onChange={e => handleQtyChange(Number(e.target.value))}
                onBlur={e => handleQtyChange(Number(e.target.value))}
                style={inputStyle}
              />
            </div>
            <div>
              <label style={labelStyle}>Price (₹)</label>
              <input
                type="number"
                min="0.05"
                step="0.05"
                value={price}
                onChange={e => handlePriceChange(Number(e.target.value))}
                onBlur={e => handlePriceChange(Number(e.target.value))}
                style={inputStyle}
              />
            </div>
          </div>

          {/* Order value summary */}
          <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            padding: "9px 12px", borderRadius: "8px",
            background: "#F9F8F6", border: "1px solid #E8E5DF",
          }}>
            <span style={{ fontSize: "12px", color: "#9B9890" }}>Order value</span>
            <span style={{ fontSize: "15px", fontWeight: "800", color: "#1A1814",
              fontVariantNumeric: "tabular-nums" }}>
              ₹{orderValue}
            </span>
          </div>

          {/* BUY / SELL — always clickable; Speed Bump fires on click when high risk */}
          {done ? (
            <div style={{
              padding: "13px", borderRadius: "8px", textAlign: "center",
              background: "#F0FDF4", border: "1px solid #BBF7D0",
            }}>
              <span style={{ fontSize: "14px", fontWeight: "700", color: "#16A34A" }}>
                ✓ Order placed successfully
              </span>
            </div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
              <button
                onClick={() => handleTradeClick("BUY")}
                disabled={loading}
                style={{
                  padding: "12px", borderRadius: "8px", border: "none",
                  background: "#16A34A", color: "#ffffff",
                  fontSize: "14px", fontWeight: "800",
                  cursor: loading ? "not-allowed" : "pointer",
                  letterSpacing: "0.04em",
                  opacity: loading ? 0.7 : 1,
                  transition: "opacity 0.15s, transform 0.1s",
                }}
                onMouseEnter={e => (e.currentTarget.style.opacity = "0.88")}
                onMouseLeave={e => (e.currentTarget.style.opacity = "1")}
              >
                BUY
              </button>
              <button
                onClick={() => handleTradeClick("SELL")}
                disabled={loading}
                style={{
                  padding: "12px", borderRadius: "8px", border: "none",
                  background: "#DC2626", color: "#ffffff",
                  fontSize: "14px", fontWeight: "800",
                  cursor: loading ? "not-allowed" : "pointer",
                  letterSpacing: "0.04em",
                  opacity: loading ? 0.7 : 1,
                  transition: "opacity 0.15s",
                }}
                onMouseEnter={e => (e.currentTarget.style.opacity = "0.88")}
                onMouseLeave={e => (e.currentTarget.style.opacity = "1")}
              >
                SELL
              </button>
            </div>
          )}

          {/* Informational note when high risk */}
          {isHigh && !done && (
            <p style={{
              fontSize: "11px", color: "#DC2626", textAlign: "center",
              lineHeight: "1.5",
            }}>
              AI model detected <strong>{analysis?.detected_pattern}</strong>.
              A commitment phrase will be required before your order executes.
            </p>
          )}
        </div>
      </div>
    </>
  );
}
