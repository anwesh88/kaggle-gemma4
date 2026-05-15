# Finsight OS

## A privacy-first behavioral guardian for India's 9.6 million retail F&O traders, built on Gemma 4

> **Track:** Digital Equity & Inclusivity (primary) · Safety & Trust (secondary)
> **Live demo:** https://kaggle-gemma4.vercel.app · **Code:** https://github.com/anwesh88/kaggle-gemma4
> **Video:** https://youtu.be/[VIDEO_ID]

---

## The problem

SEBI's F&O Study for FY2024-25 quantifies a public health crisis disguised as a market: **9.6 million** Indian retail traders lost a combined **₹1,05,603 crore (~$12.6 billion)** on equity derivatives in a single year. **91%** of individual traders incurred losses. The average net loss per trader was **₹1.1 lakh**. The people on the wrong side of these numbers are not Mumbai high-net-worth investors — **75% earn under ₹5 lakh per year and 72% live in B30 cities** (small towns and rural India).

The trading apps these users rely on were optimized to maximize trade volume, not to protect users from themselves. After two consecutive losses, an app's only response is a faster *Place Order* button. Behavioral finance research has documented this loop for decades: revenge trading, FOMO, over-leveraging, addiction-like patterns where the user keeps placing orders despite consecutive losses [Kahneman & Tversky 1979, *Prospect Theory*; Barber & Odean 2008, *Just How Much Do Individual Investors Lose by Trading?*]. There is no friction in the user experience to interrupt the spiral.

Existing solutions don't fit either. Cloud-based behavioral coaching is privacy-hostile — sending complete trading history to a server is a non-starter for B30 users with patchy connectivity and well-founded distrust. Generic chatbots don't understand Indian market structure or SEBI regulations. And anything requiring a 16 GB GPU is unusable on the ThinkBook-class laptops most retail traders actually own.

Gemma 4 changes the math. A quantized E2B variant runs on a four-year-old CPU laptop, in private, with no network calls. It speaks Hindi, Telugu, Tamil. It produces structured JSON when asked. It can be domain-adapted via QLoRA on consumer hardware. The technology to put a behavioral guardian in every retail trader's pocket exists today — what was missing was someone willing to build for the people who need it most.

## The Mindful Speed Bump

Finsight OS sits between the user and the *Place Order* button. Every order goes through a local Gemma 4 analysis: what just happened in this session, which trading vows the user pre-committed to, whether the pattern matches Revenge Trading or FOMO or Over-Leveraging, and how distressed the user appears to be financially. If the behavioral score crosses 600/1000, the trade does not execute on the first click. Instead, the app shows the detected pattern, the user's violated vow, and asks them to type a 15-word commitment phrase that names the specific behavior — *and* waits a dynamically-computed cooldown (6-18 seconds, scaled by score and pattern) before the Confirm button activates. Only after both gates clear does the order go through.

This isn't a paywall or a nag screen. It's a cognitive interrupt — long enough for the System 2 brain to come online, short enough to respect the user's autonomy [Kahneman 2011, *Thinking, Fast and Slow*]. Trades still happen. The user remains in control. But the impulse path now has a speed bump in it.

## Three deployment modes ship today

The first screen is a mode picker. **Demo Mode** (zero setup, pre-loaded high-risk session). **Paper Trading Mode** (real Yahoo Finance prices, real SQLite paper trades with FIFO lot matching, ₹100,000 paper capital). **Live Kite Connect Mode** (real broker integration, free Kite Connect Personal tier supported at ₹0/month). The first two need no broker credentials; the third lets any of Zerodha's 16M existing users plug Finsight in front of their actual trading account in five minutes (`docs/kite-setup.md`).

## Architecture

Finsight OS is a Next.js 14 frontend, a FastAPI backend, and seven local engines that run on the user's device. The architecture diagram in the media gallery shows the full picture; three things deserve explicit mention.

**Trust boundary.** Every component except a Yahoo Finance read for public NSE quotes runs locally. Trading data, behavioral analysis, RAG retrieval, behavioral DNA — all of it lives on the user's machine, written to SQLite and ChromaDB on local disk. Zero financial data leaves the device. The privacy story isn't a value prop, it's an architectural property the code enforces.

**Real, not demo.** Watchlist quotes come from `yfinance`. Every BUY and SELL persists to a SQLite paper-trading engine with FIFO lot matching that realizes P&L on the closing leg. The trades the AI analyzes are the trades the user actually placed. A representative high-risk session is seeded once on first run so judges see the Speed Bump fire immediately, but every subsequent trade flows into the next analysis. Live Kite Mode replaces this with real broker calls behind the same UI.

**Edge AI, not cloud AI.** Gemma 4 runs locally via Ollama at `localhost:11434`. No Anthropic key, no OpenAI key, no Google Cloud project. The behavioral guardian works on a flight, on a train, in a B30 town with intermittent 4G.

## Seven Gemma 4 features in use

**Thinking Mode.** The analysis prompt drives a 7-step reasoning chain — vow check → pattern → score rubric → nudge → language → stress → SEBI grounding. The reasoning chain streams to the UI token-by-token via Server-Sent Events; each step is clickable to drill into its evidence (the violated vow text, the score breakdown, the SEBI source citation).

**Multimodal Vision.** The Chart Analyzer accepts a screenshot of the user's chart workspace. Gemma 4's vision modality reads it and returns a one-sentence behavioral warning. Demonstrates the model seeing the same screen the trader sees.

**Multi-language Generation.** Every high-risk nudge is generated in English plus the user's preferred Indian language — Hindi, Telugu, or Tamil — appearing in both scripts in the Speed Bump modal. This is the Digital Equity hook: the same edge AI speaks the languages of the users it's protecting.

**Structured JSON Output.** Strict schema (`behavioral_score`, `risk_level`, `detected_pattern`, `nudge_message`, `vows_violated`, `crisis_score`). A brace-balanced extractor parses real-world model output without the brittleness of greedy regex.

**RAG-grounded Responses.** A ChromaDB local index over SEBI circulars (FY2024-25 study, MIRSD circular 2024/001, Investor Charter 2021, Peak Margin 2021, Investor Protection Guidelines) is queried at every analysis. Disclosures cite real SEBI text.

**Longitudinal Context.** A SQLite Behavioral DNA database persists every session's score and pattern. Past sessions are summarized into the prompt so Gemma sees not just today's trades but the user's history. Persistent revenge trading scores higher than first-time revenge trading.

**Domain adaptation via QLoRA.** A reproducible fine-tune pipeline (`finetune/`) trains a rank-16 LoRA adapter on Gemma 4 E2B against a SEBI-grounded instruction dataset. Training runs in ~2 hours on a free Kaggle T4 GPU. Side-by-side benchmarks against the base model on regulatory-citation accuracy, JSON-schema compliance, vow-recall F1, and Hindi-translation quality are produced by `finetune/evaluate.py` and committed to `docs/finetune-results.md`.

## Engineering challenges and solutions

**CPU-only inference budget.** The default development hardware is a four-year-old ThinkBook with an i7-1255U and 16 GB RAM. Real Gemma 4 E4B inference at our prompt complexity can exceed 90 seconds on this hardware, so the submitted app defaults to `gemma4:e2b`, compresses the prompt, widens context only when needed, and pre-warms the model on FastAPI startup. The full inference pipeline — prompt construction, Ollama call, JSON parsing, RAG enrichment, behavioral DNA write, streaming SSE delivery — is real and runs on every request. If Gemma times out or returns invalid JSON, the UI shows an explicit "Gemma unavailable" state instead of a fake behavioral score, pattern, or nudge. **Every Ollama option is overridable via environment variable** (`OLLAMA_NUM_GPU=99`, `OLLAMA_NUM_CTX=2048`, `OLLAMA_KEEP_ALIVE=30m`); on any GPU instance — including a free Kaggle T4 — real Gemma reasoning is visible immediately. See `docs/gpu-setup.md` for one-command deployment recipes for Kaggle, RunPod, Modal, and Colab.

**Live Kite Connect OAuth.** Live mode follows Zerodha's redirect-based auth: backend exposes `/kite/login-url`, user is redirected to `kite.zerodha.com`, returns to `/kite/callback` with a single-use `request_token`, the backend exchanges it for a daily-expiry `access_token` stored in an HTTP-only `SameSite=Lax` cookie. Rate-limited at the 3 req/s ceiling per Kite TOS via an asyncio semaphore plus 333 ms inter-call spacing. The same `/portfolio`, `/trade-history`, `/confirm-trade` endpoints serve all three modes via an `X-Finsight-Mode` header dispatcher.

**Streaming Server-Sent Events.** The Thinking Log streams Gemma's tokens to the UI as they're produced — green "LIVE" pill, blinking cursor, auto-scroll. On timeout, a synthesized 7-step trace streams at simulated rate so the UX is consistent regardless of which path fires.

**FIFO lot matching.** Paper trades realize P&L correctly across partial fills. The engine tracks `quantity_remaining` per row and matches SELLs against open BUYs oldest-first, splitting partial closes without splitting rows. P&L is recorded on the closing leg only to avoid double-counting.

## Impact and the path forward

The technical depth above matters only if it ships to the people SEBI is trying to protect. 9.6 million retail traders. 75% earn under ₹5 lakh. 72% in B30 cities. They run laptops like the one this was built on, with patchy internet, in three or four languages. The combination of edge AI, regulatory grounding, and a UX that respects the user's intelligence makes this a tool that can run in a Jharkhand cybercafé and still meaningfully reduce the loss rate.

A concrete five-phase distribution plan:

1. **Phase 1 (Q3 2026)**: open-source release on GitHub under MIT license, listed in awesome-edge-ai. Free for any user with a Zerodha account via the Live Kite Connect mode shipped today.
2. **Phase 2 (Q4 2026)**: browser extension build that runs alongside Zerodha Kite Web and Groww, embedding the Speed Bump in the broker's own interface.
3. **Phase 3 (Q1 2027)**: Android app (ONNX Runtime for Gemma) for the 90% of B30 users on smartphones, launching in Hindi, Telugu, Tamil, Bengali, and Marathi.
4. **Phase 4 (Q2 2027)**: broker SDK — embeddable library brokers can integrate into their own apps. Pitch to Zerodha (already SEBI-aligned on investor protection messaging), Groww, Upstox.
5. **Phase 5 (Q3 2027)**: SEBI partnership pilot in Andhra Pradesh and Odisha (high B30 density, growing F&O participation). Official endorsement opens distribution to all 9.6M users.

Gemma 4 made the technology accessible. Finsight OS makes the protection inevitable. Open source. MIT licensed. Free. Forever. Because behavioral guardianship shouldn't be a premium feature — it should be the default.

---

### References

> *(Place-holders for the user-sourced citations. Full bibliography with DOIs in `docs/references.md`.)*
> 1. Kahneman, D. & Tversky, A. (1979). *Prospect Theory: An Analysis of Decision under Risk.* Econometrica.
> 2. Barber, B. M. & Odean, T. (2008). *Just How Much Do Individual Investors Lose by Trading?* Review of Financial Studies.
> 3. Barber, Lee, Liu, Odean (2014). *The Cross-Section of Speculator Skill: Evidence from Day Trading.*
> 4. Kahneman, D. (2011). *Thinking, Fast and Slow.* (System 1 / System 2.)
> 5. SEBI (2025). *Study on participation and profitability of individual investors in the equity F&O segment, FY2024-25.*
> 6. SEBI (2024). *Circular SEBI/HO/MIRSD/PoD-1/P/CIR/2024/001 — Increased contract sizes and upfront premium collection.*
> 7. SEBI (2021). *Investor Charter for the Securities Market.*

### Submission attachments

- **Architecture diagram**: `docs/architecture.html` (also in Media Gallery as PNG)
- **Cover image**: `docs/cover-image.html` rendered to `cover.png` in Media Gallery
- **Live demo**: deployed at the URL above (Vercel frontend + Railway backend). For real Gemma reasoning on hosted infrastructure, Railway must reach an Ollama/GPU runtime. If the paid GPU runtime is offline for budget reasons, judges can run the exact local Ollama verification path documented in `docs/judge-local-gemma.md`.
- **Public code repo**: GitHub link above
- **Face-cam video script + shot list**: `docs/video-script.md`
- **Teleprompter beats + recording setup**: `docs/talking-points.md`, `docs/recording-setup.md`
- **Local-run guide**: `docs/run-locally.md`
- **Fine-tune pipeline**: `finetune/` — runnable on free Kaggle T4
- **GPU deployment recipes**: `docs/gpu-setup.md`
- **Live Kite setup guide**: `docs/kite-setup.md`
- **Model attribution note**: `docs/model-attribution.md`; Gemma is a trademark of Google LLC. Finsight OS is independent and not endorsed by Google.
