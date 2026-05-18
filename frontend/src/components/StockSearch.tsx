"use client";

/**
 * Shared paper/live stock picker + watchlist + order surface.
 *
 * - Kite mode uses broker-backed instrument search and real order placement.
 * - Paper mode keeps the same interaction model with a compact local catalogue
 *   plus free-form symbol add, then routes orders to /confirm-trade.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useMode } from "@/contexts/ModeContext";
import type { BehavioralAnalysis } from "@/types";

interface Match {
  instrument_token: number;
  tradingsymbol: string;
  name: string;
  segment: string;
  exchange: string;
  instrument_type: string;
  lot_size: number;
}

interface SelectedSymbol {
  tradingsymbol: string;
  exchange: string;
  name: string;
  instrument_type: string;
  lot_size: number;
  instrument_token: number;
}

const PAPER_MATCHES: Match[] = [
  { instrument_token: 1, tradingsymbol: "RELIANCE", name: "Reliance Industries", segment: "NSE", exchange: "NSE", instrument_type: "EQ", lot_size: 1 },
  { instrument_token: 2, tradingsymbol: "INFY", name: "Infosys", segment: "NSE", exchange: "NSE", instrument_type: "EQ", lot_size: 1 },
  { instrument_token: 3, tradingsymbol: "TCS", name: "Tata Consultancy Services", segment: "NSE", exchange: "NSE", instrument_type: "EQ", lot_size: 1 },
  { instrument_token: 4, tradingsymbol: "HDFCBANK", name: "HDFC Bank", segment: "NSE", exchange: "NSE", instrument_type: "EQ", lot_size: 1 },
  { instrument_token: 5, tradingsymbol: "ICICIBANK", name: "ICICI Bank", segment: "NSE", exchange: "NSE", instrument_type: "EQ", lot_size: 1 },
  { instrument_token: 6, tradingsymbol: "SBIN", name: "State Bank of India", segment: "NSE", exchange: "NSE", instrument_type: "EQ", lot_size: 1 },
  { instrument_token: 7, tradingsymbol: "ITC", name: "ITC", segment: "NSE", exchange: "NSE", instrument_type: "EQ", lot_size: 1 },
  { instrument_token: 8, tradingsymbol: "LT", name: "Larsen & Toubro", segment: "NSE", exchange: "NSE", instrument_type: "EQ", lot_size: 1 },
  { instrument_token: 9, tradingsymbol: "MARUTI", name: "Maruti Suzuki", segment: "NSE", exchange: "NSE", instrument_type: "EQ", lot_size: 1 },
  { instrument_token: 10, tradingsymbol: "SUNPHARMA", name: "Sun Pharma", segment: "NSE", exchange: "NSE", instrument_type: "EQ", lot_size: 1 },
];

function watchlistKey(mode: string | null) {
  return mode === "kite" ? "finsight.kite.watchlist.v1" : "finsight.paper.watchlist.v1";
}

function loadWatchlist(mode: string | null): SelectedSymbol[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(watchlistKey(mode)) || "[]");
  } catch {
    return [];
  }
}

function saveWatchlist(mode: string | null, list: SelectedSymbol[]) {
  try {
    localStorage.setItem(watchlistKey(mode), JSON.stringify(list));
  } catch {
    // localStorage is best-effort only.
  }
}

interface Props {
  analysis?: BehavioralAnalysis | null;
  onChange?: (symbols: SelectedSymbol[]) => void;
  onAfterOrder?: () => void | Promise<void>;
}

function computeCooldown(analysis: BehavioralAnalysis | null | undefined): number {
  if (!analysis || analysis.risk_level !== "high") return 0;
  const score = analysis.behavioral_score;
  let seconds = Math.max(6, Math.min(14, Math.round(6 + (score - 600) * 0.023)));
  switch (analysis.detected_pattern) {
    case "Addiction Loop":
      seconds = Math.min(18, Math.round(seconds * 1.4));
      break;
    case "Revenge Trading":
      seconds = Math.min(18, Math.round(seconds * 1.15));
      break;
    case "Over-Leveraging":
      seconds = Math.min(18, Math.round(seconds * 1.1));
      break;
    case "FOMO":
      seconds = Math.max(6, Math.round(seconds * 0.95));
      break;
    default:
      break;
  }
  return seconds;
}

export function StockSearch({ analysis, onChange, onAfterOrder }: Props) {
  const { mode } = useMode();
  const isKite = mode === "kite";

  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<Match[]>([]);
  const [open, setOpen] = useState(false);
  const [searching, setSearching] = useState(false);
  const [watchlist, setWatchlist] = useState<SelectedSymbol[]>([]);
  const [order, setOrder] = useState<null | {
    sym: SelectedSymbol;
    side: "BUY" | "SELL";
    qty: number;
    product: "MIS" | "CNC";
    orderType: "MARKET" | "LIMIT";
    limitPrice: string;
    typedCommitment: string;
    placing: boolean;
    error: string | null;
    success: string | null;
  }>(null);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [prices, setPrices] = useState<Record<string, { last: number; pct: number; available: boolean }>>({});
  const [cooldownMs, setCooldownMs] = useState(0);
  const cooldownTotal = computeCooldown(analysis);
  const isHighRisk = analysis?.risk_level === "high";
  const requiredCommitment = analysis?.nudge_message ?? "";
  const requiresCommitment = isHighRisk && requiredCommitment.length > 0;

  useEffect(() => {
    setWatchlist(loadWatchlist(mode));
  }, [mode]);

  useEffect(() => {
    onChange?.(watchlist);
  }, [watchlist, onChange]);

  useEffect(() => {
    if (watchlist.length === 0) {
      setPrices({});
      return;
    }

    let cancelled = false;
    const symbols = watchlist.map(s => s.tradingsymbol);

    async function fetchPrices() {
      try {
        const r = await api.quotesLookup(symbols);
        if (cancelled) return;
        const map: Record<string, { last: number; pct: number; available: boolean }> = {};
        for (const q of r.quotes) {
          map[q.symbol] = { last: q.last_price, pct: q.change_pct, available: q.available };
        }
        setPrices(map);
      } catch (e) {
        if (!cancelled) console.error("quotesLookup failed:", e);
      }
    }

    fetchPrices();
    const id = setInterval(fetchPrices, 30_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [watchlist]);

  useEffect(() => {
    if (!open) return;
    function onDocMouseDown(e: MouseEvent) {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocMouseDown);
    return () => document.removeEventListener("mousedown", onDocMouseDown);
  }, [open]);

  useEffect(() => {
    if (!order || !requiresCommitment || cooldownTotal <= 0) {
      setCooldownMs(0);
      return;
    }

    setCooldownMs(cooldownTotal * 1000);
    const id = setInterval(() => {
      setCooldownMs(prev => Math.max(0, prev - 100));
    }, 100);
    return () => clearInterval(id);
  }, [order?.sym.tradingsymbol, requiresCommitment, cooldownTotal]);

  const runSearch = useCallback(async (q: string) => {
    const trimmed = q.trim();
    if (!trimmed) {
      setMatches([]);
      setOpen(false);
      return;
    }

    setSearching(true);
    try {
      if (isKite) {
        const r = await api.kiteSearchInstruments(trimmed, 12);
        setMatches(r.matches);
      } else {
        const needle = trimmed.toUpperCase();
        const local = PAPER_MATCHES.filter(m =>
          m.tradingsymbol.includes(needle) || m.name.toUpperCase().includes(needle)
        );
        const exact = local.some(m => m.tradingsymbol === needle);
        const freeform: Match[] = !exact
          ? [{
              instrument_token: -1,
              tradingsymbol: needle,
              name: "Custom paper symbol",
              segment: "NSE",
              exchange: "NSE",
              instrument_type: "EQ",
              lot_size: 1,
            }]
          : [];
        setMatches([...local, ...freeform].slice(0, 12));
      }
      setOpen(true);
    } catch (e) {
      console.error("search failed:", e);
      setMatches([]);
    } finally {
      setSearching(false);
    }
  }, [isKite]);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => runSearch(query), 250);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, runSearch]);

  function addToWatchlist(m: Match) {
    const sym: SelectedSymbol = {
      tradingsymbol: m.tradingsymbol,
      exchange: m.exchange,
      name: m.name,
      instrument_type: m.instrument_type,
      lot_size: m.lot_size,
      instrument_token: m.instrument_token,
    };

    setWatchlist(prev => {
      if (prev.find(x => x.tradingsymbol === sym.tradingsymbol && x.exchange === sym.exchange)) {
        return prev;
      }
      const next = [...prev, sym];
      saveWatchlist(mode, next);
      return next;
    });
    setQuery("");
    setOpen(false);
  }

  function removeFromWatchlist(sym: SelectedSymbol) {
    setWatchlist(prev => {
      const next = prev.filter(x =>
        !(x.tradingsymbol === sym.tradingsymbol && x.exchange === sym.exchange)
      );
      saveWatchlist(mode, next);
      return next;
    });
  }

  function openOrder(sym: SelectedSymbol, side: "BUY" | "SELL") {
    const ltp = prices[sym.tradingsymbol]?.last;
    setOrder({
      sym,
      side,
      qty: sym.lot_size > 1 ? sym.lot_size : 1,
      product: "MIS",
      orderType: "MARKET",
      limitPrice: ltp && ltp > 0 ? ltp.toFixed(2) : "",
      typedCommitment: "",
      placing: false,
      error: null,
      success: null,
    });
  }

  async function submitOrder() {
    if (!order) return;
    const commitmentMatches = requiredCommitment.length > 0 &&
      order.typedCommitment.trim().toLowerCase() === requiredCommitment.trim().toLowerCase();
    if (requiresCommitment && (!commitmentMatches || cooldownMs > 0)) {
      setOrder({
        ...order,
        error: cooldownMs > 0
          ? "Reflection timer is still running."
          : "Type the commitment phrase exactly before placing this order.",
      });
      return;
    }
    if (order.qty <= 0) {
      setOrder({ ...order, error: "Quantity must be > 0" });
      return;
    }
    if (order.orderType === "LIMIT" && (!order.limitPrice || Number(order.limitPrice) <= 0)) {
      setOrder({ ...order, error: "Set a positive limit price" });
      return;
    }

    setOrder({ ...order, placing: true, error: null });
    try {
      let orderId = "";
      if (isKite) {
        const r = await api.kitePlaceOrder({
          symbol: order.sym.tradingsymbol,
          quantity: order.qty,
          transaction_type: order.side,
          product: order.product,
          order_type: order.orderType,
          price: order.orderType === "LIMIT" ? Number(order.limitPrice) : undefined,
          exchange: order.sym.exchange as "NSE" | "BSE",
        });
        orderId = r.order_id;
      } else {
        const marketPrice = prices[order.sym.tradingsymbol]?.last;
        const paperPrice = order.orderType === "LIMIT"
          ? Number(order.limitPrice)
          : marketPrice;
        if (!paperPrice || paperPrice <= 0) {
          setOrder({
            ...order,
            placing: false,
            error: "Live quote unavailable — use a LIMIT price for this paper order.",
          });
          return;
        }
        const r = await api.confirmTrade(
          order.sym.tradingsymbol,
          order.qty,
          paperPrice,
          order.side,
        );
        orderId = r.order_id;
      }

      setOrder({ ...order, placing: false, success: `Order ${orderId} placed` });
      await onAfterOrder?.();
      setTimeout(() => setOrder(null), 1800);
    } catch (e: any) {
      const msg = e?.message || "Order rejected";
      setOrder({ ...order, placing: false, error: msg });
    }
  }

  const watchlistByKey = useMemo(
    () => Object.fromEntries(watchlist.map(s => [`${s.exchange}:${s.tradingsymbol}`, s])),
    [watchlist],
  );
  const commitmentMatches = requiredCommitment.length > 0 &&
    order?.typedCommitment.trim().toLowerCase() === requiredCommitment.trim().toLowerCase();

  return (
    <div style={{
      background: "#fff",
      border: "1px solid #16A34A33",
      borderRadius: 14,
      padding: "14px 16px",
      boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
      position: "relative",
    }}>
      <div style={{
        fontSize: 13,
        fontWeight: 800,
        color: "#1A1814",
        letterSpacing: "-0.01em",
        marginBottom: 10,
      }}>
        Search & Trade · {isKite ? "Live Kite" : "Paper Trading"}
      </div>

      <div ref={containerRef} style={{ position: "relative" }}>
        <input
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onFocus={() => { if (matches.length) setOpen(true); }}
          onKeyDown={e => { if (e.key === "Escape") setOpen(false); }}
          placeholder={isKite
            ? "Type a symbol or company name (e.g. RELIANCE, INFY, NIFTY)…"
            : "Search a paper symbol or type one to add it…"}
          style={{
            width: "100%",
            padding: "10px 12px",
            border: "1px solid #BBF7D0",
            borderRadius: 10,
            fontSize: 13,
            fontFamily: "inherit",
            outline: "none",
            background: "#F0FDF4",
          }}
        />
        {searching && (
          <span style={{ position: "absolute", right: 12, top: 11, fontSize: 11, color: "#6B6860" }}>
            …
          </span>
        )}

        {open && matches.length > 0 && (
          <div style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            left: 0,
            right: 0,
            zIndex: 10,
            background: "#fff",
            border: "1px solid #BBF7D0",
            borderRadius: 10,
            boxShadow: "0 8px 24px rgba(0,0,0,0.08)",
            maxHeight: 280,
            overflowY: "auto",
          }}>
            {matches.map(m => {
              const key = `${m.exchange}:${m.tradingsymbol}`;
              const inWL = !!watchlistByKey[key];
              return (
                <button
                  key={`${m.instrument_token}-${m.tradingsymbol}`}
                  onMouseDown={e => {
                    e.preventDefault();
                    addToWatchlist(m);
                  }}
                  disabled={inWL}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    width: "100%",
                    padding: "10px 12px",
                    background: inWL ? "#F1F5F9" : "#fff",
                    border: "none",
                    borderBottom: "1px solid #F1EEE7",
                    cursor: inWL ? "default" : "pointer",
                    textAlign: "left",
                    font: "inherit",
                    color: "#1A1814",
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 800, fontSize: 13 }}>{m.tradingsymbol}</div>
                    <div style={{ fontSize: 11, color: "#6B6860" }}>
                      {m.exchange} · {m.instrument_type} · {m.name || "—"}
                    </div>
                  </div>
                  <span style={{
                    fontSize: 11,
                    fontWeight: 700,
                    color: inWL ? "#9CA3AF" : "#16A34A",
                  }}>
                    {inWL ? "ADDED" : "+ ADD"}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {watchlist.length === 0 ? (
        <p style={{ fontSize: 12, color: "#6B6860", marginTop: 12 }}>
          Your watchlist is empty. Search a stock above to add it; then BUY, SELL, or EXIT directly from this row.
        </p>
      ) : (
        <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
          {watchlist.map(s => {
            const q = prices[s.tradingsymbol];
            const hasPrice = q && q.available && q.last > 0;
            const positive = q ? q.pct >= 0 : false;
            return (
              <div key={`${s.exchange}:${s.tradingsymbol}`} style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "8px 10px",
                border: "1px solid #E5E7EB",
                borderRadius: 10,
                background: "#FAFAFA",
                gap: 10,
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 800, fontSize: 13 }}>{s.tradingsymbol}</div>
                  <div style={{ fontSize: 11, color: "#6B6860" }}>
                    {s.exchange} · {s.instrument_type} · lot {s.lot_size}
                  </div>
                </div>
                <div style={{ textAlign: "right", minWidth: 72 }}>
                  {hasPrice ? (
                    <>
                      <div style={{ fontWeight: 800, fontSize: 13, color: "#1A1814" }}>
                        ₹{q.last.toFixed(2)}
                      </div>
                      <div style={{
                        fontSize: 11,
                        fontWeight: 700,
                        color: positive ? "#15803D" : "#DC2626",
                      }}>
                        {positive ? "+" : ""}{q.pct.toFixed(2)}%
                      </div>
                    </>
                  ) : (
                    <div style={{ fontSize: 11, color: "#9CA3AF" }}>…</div>
                  )}
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  <ActionBtn label="BUY" onClick={() => openOrder(s, "BUY")} bg="#16A34A" />
                  <ActionBtn label="SELL" onClick={() => openOrder(s, "SELL")} bg="#DC2626" />
                  <ActionBtn label="EXIT" onClick={() => openOrder(s, "SELL")} bg="#1A1814" title="Square off the position" />
                  <ActionBtn label="✕" onClick={() => removeFromWatchlist(s)} bg="#9CA3AF" title="Remove from watchlist" />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {order && (
        <div style={{
          position: "fixed",
          inset: 0,
          background: "rgba(0,0,0,0.45)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          zIndex: 50,
          padding: 16,
        }}>
          <div style={{
            background: "#fff",
            borderRadius: 16,
            padding: 22,
            width: "100%",
            maxWidth: 380,
            boxShadow: "0 12px 40px rgba(0,0,0,0.2)",
          }}>
            <div style={{
              fontSize: 11,
              fontWeight: 700,
              color: order.side === "BUY" ? "#15803D" : "#DC2626",
              letterSpacing: "0.06em",
              marginBottom: 4,
            }}>
              {order.side} ORDER · {isKite ? "LIVE KITE" : "PAPER"}
            </div>
            <div style={{ fontSize: 22, fontWeight: 800, marginBottom: 2 }}>
              {order.sym.tradingsymbol}
            </div>
            <div style={{ fontSize: 12, color: "#6B6860", marginBottom: 14 }}>
              {order.sym.exchange} · {order.sym.instrument_type} · lot {order.sym.lot_size}
            </div>

            <Field label="Quantity">
              <input
                type="number"
                min={1}
                value={order.qty}
                onChange={e => setOrder({ ...order, qty: Number(e.target.value) || 0 })}
                style={input}
              />
            </Field>

            {isKite && (
              <Field label="Product">
                <select
                  value={order.product}
                  onChange={e => setOrder({ ...order, product: e.target.value as "MIS" | "CNC" })}
                  style={input}
                >
                  <option value="MIS">MIS · intraday</option>
                  <option value="CNC">CNC · delivery</option>
                </select>
              </Field>
            )}

            <Field label="Order type">
              <select
                value={order.orderType}
                onChange={e => setOrder({ ...order, orderType: e.target.value as "MARKET" | "LIMIT" })}
                style={input}
              >
                <option value="MARKET">MARKET</option>
                <option value="LIMIT">LIMIT</option>
              </select>
            </Field>

            {order.orderType === "LIMIT" && (
              <Field label="Limit price">
                <input
                  type="number"
                  step="0.05"
                  min={0}
                  value={order.limitPrice}
                  onChange={e => setOrder({ ...order, limitPrice: e.target.value })}
                  style={input}
                />
              </Field>
            )}

            {requiresCommitment && (
              <div style={{
                marginTop: 12,
                padding: "12px 14px",
                borderRadius: 10,
                border: "1px solid #FECACA",
                background: "#FEF2F2",
              }}>
                <div style={{ fontSize: 11, fontWeight: 800, color: "#DC2626", marginBottom: 6 }}>
                  Mindful Speed Bump · {analysis?.detected_pattern}
                </div>
                <div style={{ fontSize: 12, color: "#7F1D1D", lineHeight: 1.5, marginBottom: 8 }}>
                  {cooldownMs > 0
                    ? `Reflect for ${Math.ceil(cooldownMs / 1000)}s, then type the commitment phrase below.`
                    : "Type this commitment exactly before the order can proceed."}
                </div>
                <div style={{ fontSize: 12, color: "#991B1B", fontStyle: "italic", marginBottom: 8 }}>
                  “{requiredCommitment}”
                </div>
                <input
                  value={order.typedCommitment}
                  onChange={e => setOrder({ ...order, typedCommitment: e.target.value })}
                  placeholder="Type the commitment phrase…"
                  style={{
                    ...input,
                    border: `1.5px solid ${commitmentMatches ? "#16A34A" : "#FCA5A5"}`,
                    background: commitmentMatches ? "#F0FDF4" : "#fff",
                  }}
                />
              </div>
            )}

            {order.error && (
              <div style={{ marginTop: 8, fontSize: 12, color: "#B91C1C" }}>{order.error}</div>
            )}
            {order.success && (
              <div style={{ marginTop: 8, fontSize: 12, color: "#15803D", fontWeight: 700 }}>
                {order.success}
              </div>
            )}

            <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
              <button
                onClick={() => setOrder(null)}
                disabled={order.placing}
                style={{
                  flex: 1,
                  padding: "10px 12px",
                  borderRadius: 8,
                  border: "1px solid #E5E7EB",
                  background: "#fff",
                  cursor: "pointer",
                  fontWeight: 700,
                  fontSize: 13,
                }}
              >
                Cancel
              </button>
              <button
                onClick={submitOrder}
                disabled={
                  order.placing ||
                  !!order.success ||
                  (requiresCommitment && (!commitmentMatches || cooldownMs > 0))
                }
                style={{
                  flex: 2,
                  padding: "10px 12px",
                  borderRadius: 8,
                  border: "none",
                  background: order.side === "BUY" ? "#16A34A" : "#DC2626",
                  color: "#fff",
                  cursor: order.placing ? "wait" : "pointer",
                  fontWeight: 800,
                  fontSize: 13,
                  opacity: order.placing || order.success || (requiresCommitment && (!commitmentMatches || cooldownMs > 0)) ? 0.7 : 1,
                }}
              >
                {order.placing
                  ? "Placing…"
                  : order.success
                    ? "Placed ✓"
                    : requiresCommitment && cooldownMs > 0
                      ? `Reflect · ${Math.ceil(cooldownMs / 1000)}s`
                    : `Confirm ${order.side}`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ActionBtn({ label, onClick, bg, title }: {
  label: string;
  onClick: () => void;
  bg: string;
  title?: string;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      style={{
        background: bg,
        color: "#fff",
        border: "none",
        borderRadius: 6,
        padding: "5px 9px",
        fontSize: 11,
        fontWeight: 800,
        cursor: "pointer",
      }}
    >
      {label}
    </button>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ fontSize: 11, color: "#6B6860", marginBottom: 4, letterSpacing: "0.04em" }}>
        {label.toUpperCase()}
      </div>
      {children}
    </div>
  );
}

const input: React.CSSProperties = {
  width: "100%",
  padding: "8px 10px",
  border: "1px solid #E5E7EB",
  borderRadius: 8,
  fontSize: 13,
  fontFamily: "inherit",
};
