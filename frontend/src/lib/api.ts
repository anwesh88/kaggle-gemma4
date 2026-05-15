import { MODE_HEADER, MODE_STORAGE_KEY } from "@/lib/mode";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Read the user's chosen mode from localStorage. Used to thread the
 * X-Finsight-Mode header into every backend call. Falls back to "demo"
 * if no mode is set (so /health and similar work even before the picker).
 */
function currentMode(): string {
  if (typeof window === "undefined") return "demo";
  try {
    return localStorage.getItem(MODE_STORAGE_KEY) || "demo";
  } catch {
    return "demo";
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    [MODE_HEADER]:  currentMode(),
  };
  if (init?.headers) Object.assign(headers, init.headers as Record<string, string>);

  const r = await fetch(`${BASE}${path}`, {
    credentials: "include",     // forward Kite session cookie when present
    ...init,
    headers,
  });
  if (!r.ok) {
    // Try to surface the FastAPI `detail` so UI components can show the
    // real reason a request failed (e.g., Kite rejection hints) instead
    // of just a status code.
    let detail = "";
    try {
      const body = await r.json();
      detail = typeof body?.detail === "string" ? body.detail
             : typeof body?.error  === "string" ? body.error
             : "";
    } catch {/* not JSON, ignore */}
    const err = new Error(detail || `${path}: ${r.status}`);
    (err as any).status = r.status;
    (err as any).detail = detail;
    throw err;
  }
  return r.json();
}

export const api = {
  // Server health + actual configured model name (drives badges)
  health: () => req<{
    status: string;
    demo_mode: boolean;
    model: string;
    edge_ai: boolean;
    kite: import("@/types").KiteStatus;
  }>("/health"),

  // Behavioral analysis (non-streaming) + DNA history
  analyze: () => req<import("@/types").BehavioralAnalysis>("/analyze-behavior", { method: "POST", body: "{}" }),
  getDNA:  () => req<import("@/types").BehavioralDNA>("/behavioral-dna"),

  // Vows
  getVows:    () => req<{ vows: string[]; language: string }>("/trading-vows"),
  updateVows: (vows: string[], language = "en") =>
    req("/trading-vows", { method: "POST", body: JSON.stringify({ vows, preferred_language: language }) }),
  // Trades + portfolio (mode-aware on the backend)
  confirmTrade: (symbol: string, qty: number, price: number, action: "BUY" | "SELL" = "BUY") =>
    req<{ order_id: string }>("/confirm-trade", {
      method: "POST", body: JSON.stringify({ symbol, quantity: qty, price, action }),
    }),
  getTradeHistory: (limit = 20) =>
    req<import("@/types").TradeHistoryResponse>(`/trade-history?limit=${limit}`),
  getPortfolio:    () => req<import("@/types").PortfolioResponse>("/portfolio"),
  getMarketQuotes: () => req<import("@/types").MarketSnapshot>("/market-quotes"),

  /** Look up LTP + day-change for arbitrary NSE symbols via yfinance.
   *  Used by the in-app watchlist when Kite's /quote API is restricted. */
  quotesLookup: (symbols: string[]) => req<{
    quotes: Array<{
      symbol: string;
      last_price: number;
      prev_close: number;
      change: number;
      change_pct: number;
      available: boolean;
    }>;
    count: number;
  }>(`/quotes/lookup?symbols=${encodeURIComponent(symbols.join(","))}`),

  // Multimodal AI model vision — four-layer behavioral chart analysis.
  analyzeChart: async (file: File) => {
    const fd = new FormData(); fd.append("file", file);
    const r = await fetch(`${BASE}/analyze-chart`, {
      method: "POST",
      body: fd,
      headers: { [MODE_HEADER]: currentMode() },
      credentials: "include",
    });
    return r.json() as Promise<{
      insight: string;
      market_state: "trending" | "ranging" | "volatile" | "unknown" | string;
      market_structure: {
        trend: string;
        momentum: string;
        volatility: string;
        volume_confirmation: string;
        key_observation: string;
      };
      behavioral_risk: {
        fomo_probability: number;
        revenge_probability: number;
        panic_probability: number;
        overconfidence_risk: number;
        emotional_risk_level: "low" | "medium" | "high" | "unknown" | string;
        primary_concern: string;
        reasons?: {
          fomo_probability?: string;
          revenge_probability?: string;
          panic_probability?: string;
          overconfidence_risk?: string;
        };
      };
      decision_quality: {
        score: number;
        rating: "poor" | "average" | "good" | "unknown" | string;
        entry_timing: string;
        risk_reward: string;
        stop_placement: string;
        position_sizing: string;
      };
      personalized_insight: string;
      behavioral_warning: string;
      error?: string;
    }>;
  },

  // ── Live Kite Connect ────────────────────────────────────────────────
  /** Backend tells us whether KITE_API_KEY is configured + whether a session is live. */
  kiteStatus: () => req<{
    configured: boolean;
    authenticated: boolean;
    user_name?: string;
    user_id?: string;
    error?: string;
    session_source?: string | null;
    expected_redirect_url?: string;
    frontend_url?: string;
    warning?: string | null;
  }>("/kite/status"),

  /** Returns the Zerodha login URL we redirect the user to. */
  kiteLoginUrl: () => req<{ login_url: string }>("/kite/login-url"),

  /** Manual paste-flow when the configured redirect URL is unreachable. */
  kiteManualCallback: (request_token_or_url: string) =>
    req<{ ok: true; user_id: string; user_name: string }>("/kite/manual-callback", {
      method: "POST",
      body: JSON.stringify({ request_token_or_url }),
    }),

  /** Live Kite equity margins — available cash + utilised debits. */
  kiteMargins: () => req<{
    available_cash: number;
    opening_balance: number;
    utilised_debits: number;
    utilised_m2m: number;
    available: number;
    used: number;
    total: number;
  }>("/kite/margins"),

  /** Preferred live broker read model — balance, holdings, positions, trades, watchlist. */
  kiteAccountSnapshot: (symbols?: string[]) =>
    req<import("@/types").KiteAccountSnapshot>(
      `/kite/account-snapshot${symbols && symbols.length ? `?symbols=${encodeURIComponent(symbols.join(","))}` : ""}`,
    ),

  /** Long-term Zerodha holdings (T+2 settled equity). */
  kiteHoldings: () => req<{
    holdings: Array<{
      symbol: string;
      exchange: string;
      quantity: number;
      avg_price: number;
      ltp: number;
      pnl: number;
      day_change_pct: number;
    }>;
    count: number;
  }>("/kite/holdings"),

  /** Live quotes for an arbitrary symbol list (default 5-symbol watchlist). */
  kiteWatchlist: (symbols?: string[]) => req<{
    watchlist: Array<{
      symbol: string;
      last_price: number;
      open: number; high: number; low: number; close: number;
      change: number; change_pct: number; volume: number;
    }>;
    count: number;
  }>(`/kite/watchlist${symbols && symbols.length ? `?symbols=${encodeURIComponent(symbols.join(","))}` : ""}`),

  /** Fuzzy instrument search for the in-app stock picker (Kite mode only). */
  kiteSearchInstruments: (q: string, limit = 12) =>
    req<{
      matches: Array<{
        instrument_token: number;
        tradingsymbol: string;
        name: string;
        segment: string;
        exchange: string;
        instrument_type: string;
        lot_size: number;
      }>;
      count: number;
    }>(`/kite/instruments/search?q=${encodeURIComponent(q)}&limit=${limit}`),

  /** Place a real Zerodha order. Must be called AFTER the Mindful Speed Bump. */
  kitePlaceOrder: (body: {
    symbol: string;
    quantity: number;
    transaction_type: "BUY" | "SELL";
    product?: "MIS" | "CNC";
    order_type?: "MARKET" | "LIMIT";
    price?: number;
    exchange?: "NSE" | "BSE";
  }) =>
    req<{
      ok: true;
      order_id: string;
      symbol: string;
      transaction_type: "BUY" | "SELL";
      quantity: number;
      order_type: string;
      broker: "kite";
    }>("/kite/place-order", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** Logs out — backend clears the access_token cookie. */
  kiteLogout: () => req<{ ok: true }>("/kite/logout", { method: "POST", body: "{}" }),

  /** Wipes the paper-trading SQLite back to ₹100K fresh state. Mode=paper only. */
  paperReset: () => req<{ ok: true; reset: true; mode: string }>("/paper/reset", {
    method: "POST", body: "{}",
  }),
};
