export type RiskLevel = "low" | "medium" | "high";
export type Language = "en" | "hi" | "te" | "ta";

export interface Trade {
  trade_id: string; symbol: string; action: "BUY" | "SELL";
  quantity: number; price: number; timestamp: string;
  pnl: number | null; is_loss: boolean;
}

export interface MarginData {
  available: number; used: number; total: number;
}

export interface BehavioralAnalysis {
  behavioral_score: number;
  risk_level: RiskLevel;
  detected_pattern: string;
  nudge_message: string;
  nudge_message_local: string;
  vows_violated: string[];
  crisis_score: number;
  crisis_detected: boolean;
  sebi_disclosure: string | null;
  sebi_source: string | null;
  thinking_log: string | null;
  chart_insight: string | null;
  inference_seconds: number | null;   // Real local-CPU Fin AI latency
  analysis_source?: "deterministic_fast_path" | "deterministic_preview" | "gemma_backed" | "unavailable";
  model_used?: boolean;
  timings_ms?: Record<string, number>;
}

export interface DNASession {
  date: string; score: number; pattern: string;
}

export interface BehavioralDNA {
  total_sessions: number;
  dominant_pattern: string;
  avg_score: number;
  high_risk_rate: number;
  worst_score: number;
  streak_days: number;
  sessions: DNASession[];
}

// Live NSE quote feed (Yahoo Finance via /market-quotes)
export interface Quote {
  symbol: string;
  yahoo_symbol: string;
  price: number;
  previous_close: number;
  change_percent: number;
  currency: string;
}

export type MarketState = "open" | "pre-open" | "closed" | "weekend";

export interface MarketSnapshot {
  quotes: Quote[];
  fetched_at: string;          // ISO 8601 UTC
  source: "yahoo" | "fallback" | "stale-cache";
  market_open: boolean;
  market_state: MarketState;
}

// Paper trading engine (backend/paper_trading.py)
export interface PaperTrade {
  order_id: string;
  symbol: string;
  action: "BUY" | "SELL";
  quantity: number;
  price: number;
  timestamp: string;            // ISO 8601 UTC
  quantity_remaining: number;
  realized_pnl: number | null;
  is_loss: boolean | null;
}

export interface SessionPnL {
  since: string;
  total_trades: number;
  closed_trades: number;
  realized_pnl: number;
  loss_count: number;
}

export interface TradeHistoryResponse {
  trades: PaperTrade[];
  session_pnl: SessionPnL;
}

export interface OpenPosition {
  symbol: string;
  side: "BUY" | "SELL";          // BUY = long, SELL = short
  quantity: number;
  avg_price: number;
  exchange?: string;
  product?: string;
  pnl?: number;
  m2m?: number;
  last_price?: number;
  exposure?: number;
}

export interface PortfolioResponse {
  positions: OpenPosition[];
  session_pnl: SessionPnL;
}

export interface KiteStatus {
  configured: boolean;
  authenticated: boolean;
  user_name?: string;
  user_id?: string;
  error?: string;
  session_source?: string | null;
  expected_redirect_url?: string;
  frontend_url?: string;
  warning?: string | null;
}

export interface KiteMargins {
  available_cash: number;
  opening_balance: number;
  utilised_debits: number;
  utilised_m2m: number;
  available: number;
  used: number;
  total: number;
}

export interface KiteHolding {
  symbol: string;
  exchange: string;
  quantity: number;
  avg_price: number;
  ltp: number;
  pnl: number;
  day_change_pct: number;
}

export interface KiteWatchlistQuote {
  symbol: string;
  last_price: number;
  open: number;
  high: number;
  low: number;
  close: number;
  change: number;
  change_pct: number;
  volume: number;
}

export interface KiteAccountSummary extends SessionPnL {
  open_pnl: number;
  open_pnl_source: "exact" | "derived" | "unknown";
  realized_pnl_source: "exact" | "derived" | "unknown";
  open_positions_count: number;
  holdings_count: number;
  net_day_pnl: number;
  available_cash: number;
  utilised_margin: number;
  total_exposure: number;
  exposure_concentration: number;
  inferred_loss_streak: number;
}

export interface KiteAccountSnapshot {
  margins: KiteMargins;
  holdings: KiteHolding[];
  positions: OpenPosition[];
  trades: PaperTrade[];
  watchlist: KiteWatchlistQuote[];
  watchlist_symbols: string[];
  summary: KiteAccountSummary;
  warnings: string[];
}
