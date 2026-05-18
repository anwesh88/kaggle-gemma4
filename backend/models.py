from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime
from enum import Enum

class Language(str, Enum):
    EN = "en"
    HI = "hi"
    TE = "te"
    TA = "ta"

class Trade(BaseModel):
    trade_id: str
    symbol: str
    action: Literal["BUY", "SELL"]
    quantity: int
    price: float
    timestamp: datetime
    pnl: Optional[float] = None
    is_loss: bool = False

class MarginData(BaseModel):
    available: float
    used: float
    total: float

    @property
    def usage_ratio(self) -> float:
        return self.used / self.total if self.total > 0 else 0.0

class BehavioralPattern(str, Enum):
    REVENGE_TRADING = "Revenge Trading"
    FOMO = "FOMO"
    OVER_LEVERAGING = "Over-Leveraging"
    PANIC_SELLING = "Panic Selling"
    HEALTHY = "Healthy Trading"
    ADDICTION_LOOP = "Addiction Loop"  # NEW: 75% continue despite losses

class TradingContext(BaseModel):
    recent_trades: list[Trade]
    margin: MarginData
    trading_vows: list[str] = []
    session_start: datetime = Field(default_factory=datetime.now)
    preferred_language: Language = Language.EN
    historical_sessions: int = 0         # From BehavioralDNA
    historical_loss_rate: float = 0.0   # From BehavioralDNA
    source_mode: Literal["demo", "paper", "kite"] = "demo"
    day_realized_pnl: Optional[float] = None
    open_pnl: Optional[float] = None
    open_positions_count: int = 0
    holdings_count: int = 0
    total_exposure: float = 0.0
    exposure_concentration: float = 0.0
    inferred_loss_streak: int = 0
    realized_pnl_source: Literal["exact", "derived", "unknown"] = "unknown"
    open_pnl_source: Literal["exact", "derived", "unknown"] = "unknown"
    portfolio_positions: list[str] = Field(default_factory=list)
    portfolio_holdings: list[str] = Field(default_factory=list)
    analysis_notes: list[str] = Field(default_factory=list)

class BehavioralAnalysis(BaseModel):
    behavioral_score: int = Field(ge=0, le=1000)
    risk_level: Literal["low", "medium", "high"]
    detected_pattern: str
    nudge_message: str                  # 15-word commitment phrase
    nudge_message_local: str = ""       # Same phrase in user's language
    sebi_disclosure: Optional[str] = None
    sebi_source: Optional[str] = None  # RAG citation
    thinking_log: Optional[str] = None
    crisis_detected: bool = False       # Elevated session-stress flag
    crisis_score: int = 0              # 0-100 session-stress severity
    chart_insight: Optional[str] = None  # From multimodal analysis
    vows_violated: list[str] = []
    inference_seconds: Optional[float] = None  # Real local-CPU Gemma latency
    analysis_source: Literal["deterministic_fast_path", "deterministic_preview", "gemma_backed", "unavailable"] = "gemma_backed"
    model_used: bool = True
    timings_ms: dict[str, float] = Field(default_factory=dict)

class DNASession(BaseModel):
    session_id: str
    date: datetime
    trades_count: int
    loss_count: int
    pattern: str
    behavioral_score: int
    max_margin_used: float

class TradeRequest(BaseModel):
    symbol: str
    quantity: int
    price: float
    action: Literal["BUY", "SELL"] = "BUY"
    chart_image_b64: Optional[str] = None  # For multimodal analysis

class VowsUpdate(BaseModel):
    vows: list[str]
    preferred_language: Language = Language.EN
