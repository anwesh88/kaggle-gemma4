# Finsight OS

## A privacy-first behavioral guardian for stock market participants, built on Gemma 4

> **Track:** Digital Equity & Inclusivity (primary) · Safety & Trust (secondary)
> **Live demo:** https://kaggle-gemma4.vercel.app · **Code:** https://github.com/anwesh88/kaggle-gemma4
> **Diagrams:** [Architecture](https://finsight-os-diagrams.vercel.app/#architecture) · [Data pipeline](https://finsight-os-diagrams.vercel.app/#data-pipeline)
> **Video:** https://youtu.be/[VIDEO_ID]

---

## The problem

India's retail market has become radically easier to enter; it has not become equally safe to navigate. In the cash market, SEBI found that **7 out of 10** individual intraday traders lose money. In equity derivatives, the failure mode becomes impossible to ignore: SEBI's FY2024-25 study found **9.6 million** Indian retail F&O traders lost a combined **₹1,05,603 crore (~$12.6 billion)** in a single year, with **91%** of individual traders incurring losses and an average net loss of **₹1.1 lakh**. F&O is the sharpest proof point, not the product boundary.

The apps serving self-directed market participants were optimized for throughput, not reflection. After two consecutive losses, the interface usually offers the same frictionless *Place Order* button. Behavioral finance research has documented the loop for decades: revenge trading, FOMO, over-leveraging, and repeated action under loss pressure [Kahneman & Tversky 1979, *Prospect Theory*; Barber & Odean 2008, *Just How Much Do Individual Investors Lose by Trading?*]. There is almost no product-layer intervention at the exact moment when a costly impulse becomes an executed order.

Existing solutions miss the shape of the problem. Cloud-based behavioral coaching is privacy-hostile because it requires exporting complete trading history. Generic chatbots are detached from the order flow, weak on Indian market structure, and easy to ignore when the next trade is one click away. And solutions that assume a 16 GB GPU exclude the ordinary laptops many first-generation market participants actually use.

Gemma 4 changes the math. A quantized E2B variant runs on a four-year-old CPU laptop, in private, with no network calls. It speaks Hindi, Telugu, Tamil. It produces structured JSON when asked. It can be domain-adapted via QLoRA on consumer hardware. The technology to place a behavioral safeguard beside every self-directed market participant exists today — what was missing was a product willing to intervene at the moment of action, without taking custody of the user's data or agency.

## The Mindful Speed Bump

Finsight OS maintains a local behavioral view of the current session: recent trades, pre-committed trading vows, detected patterns such as Revenge Trading, FOMO, or Over-Leveraging, and the amount of risk pressure the session is showing. In the current demo trade flow, when the latest analysis is marked high risk, Finsight places a *Mindful Speed Bump* in front of the order: it shows the detected pattern and any violated vows, asks the user to retype a model-generated commitment phrase, and enforces a dynamically computed cooldown of 6-18 seconds before confirmation unlocks.

This isn't a paywall or a nag screen. It's a cognitive interrupt — long enough for the System 2 brain to come online, short enough to respect the user's autonomy [Kahneman 2011, *Thinking, Fast and Slow*]. The user remains in control. But the impulse path now has a speed bump in it.

## Three deployment modes ship today

The first screen is a mode picker. **Demo Mode** (zero setup, pre-loaded high-risk session). **Paper Trading Mode** (real Yahoo Finance prices, real SQLite paper trades with FIFO lot matching, ₹100,000 paper capital). **Live Kite Connect Mode** (real broker integration, free Kite Connect Personal tier supported at ₹0/month). The first two need no broker credentials; the third lets any of Zerodha's 16M existing users plug Finsight in front of their actual trading account in five minutes (`docs/kite-setup.md`).

## Architecture

Finsight OS is a Next.js 14 frontend, a FastAPI backend, and seven local engines that run on the user's device. The architecture diagram in the media gallery shows the full picture; three things deserve explicit mention.

**Trust boundary.** Every component except a Yahoo Finance read for public NSE quotes runs locally by default. Behavioral scores, nudges, RAG retrieval, and Behavioral DNA stay on the user's machine, written to SQLite and ChromaDB on local disk. Optional Live Kite mode opens only the user-authorized broker path needed for account reads and orders; the behavioral intelligence itself stays local. The privacy story isn't a value prop, it's an architectural property the code enforces.

**Real, not demo.** Watchlist quotes come from `yfinance`. Every BUY and SELL persists to a SQLite paper-trading engine with FIFO lot matching that realizes P&L on the closing leg. The trades the AI analyzes are the trades the user actually placed. A representative high-risk session is seeded once on first run so judges see the Speed Bump fire immediately, but every subsequent trade flows into the next analysis. Live Kite Mode replaces this with real broker calls behind the same UI.

**Edge AI, not cloud AI.** Gemma 4 runs locally via Ollama at `localhost:11434`. No Anthropic key, no OpenAI key, no Google Cloud project. The behavioral guardian works on a flight, on a train, in a B30 town with intermittent 4G.

## Seven Gemma 4 capabilities in use

**Auditable analysis trace.** Gemma returns structured behavioral output from a prompt that asks it to reason over vows, patterns, score rubric, and localized nudges. The UI streams a six-step evidence trace assembled from the real context plus Gemma's completed JSON response, so every intervention remains inspectable without claiming access to hidden model reasoning.

**Multimodal Vision.** The Chart Analyzer accepts a screenshot of the user's chart workspace. Gemma 4's vision modality reads it and returns a one-sentence behavioral warning. Demonstrates the model seeing the same screen the trader sees.

**Multi-language Generation.** Every high-risk nudge is generated in English plus the user's preferred Indian language — Hindi, Telugu, or Tamil — appearing in both scripts in the Speed Bump modal. This is the Digital Equity hook: the same edge AI speaks the languages of the users it's protecting.

**Structured JSON Output.** Strict schema (`behavioral_score`, `risk_level`, `detected_pattern`, `nudge_message`, `vows_violated`). A brace-balanced extractor parses real-world model output without the brittleness of greedy regex.

**RAG-grounded Disclosures.** A ChromaDB local index over SEBI circulars (FY2024-25 study, MIRSD circular 2024/001, Investor Charter 2021, Peak Margin 2021, Investor Protection Guidelines) is queried at every analysis. The app attaches locally retrieved SEBI disclosures to completed model responses.

**Longitudinal Context.** A SQLite Behavioral DNA database persists every session's score and pattern. Past sessions are summarized into the prompt so Gemma sees not just today's trades but the user's history. Persistent revenge trading scores higher than first-time revenge trading.

**Domain adaptation via QLoRA.** A reproducible fine-tune pipeline (`finetune/`) trains a rank-16 LoRA adapter on Gemma 4 E2B against a SEBI-grounded instruction dataset. Training runs in ~2 hours on a free Kaggle T4 GPU. Side-by-side benchmarks against the base model on regulatory-citation accuracy, JSON-schema compliance, vow-recall F1, and Hindi-translation quality are produced by `finetune/evaluate.py` and committed to `docs/finetune-results.md`.

## Engineering challenges and solutions

**CPU-only inference budget.** The default development hardware is a four-year-old ThinkBook with an i7-1255U and 16 GB RAM. Real Gemma 4 E4B inference at our prompt complexity exceeds 90 seconds on this hardware. We compress the prompt ~30%, slim the JSON schema, pre-warm the model on FastAPI startup (saves the 25-40s weight-loading cold start), and return an explicit Gemma-unavailable state when the timeout is exceeded. The full inference pipeline - prompt construction, Ollama call, JSON parsing, RAG enrichment, behavioral DNA write, streaming SSE delivery - is real and runs on every request; no behavioral insight is fabricated when the model cannot complete. **Every Ollama option is overridable via environment variable** (`OLLAMA_NUM_GPU=99`, `OLLAMA_NUM_CTX=2048`, `OLLAMA_KEEP_ALIVE=30m`); on any GPU instance — including a free Kaggle T4 — real Gemma reasoning is visible immediately. See `docs/gpu-setup.md` for one-command deployment recipes for Kaggle, RunPod, Modal, and Colab.

**Live Kite Connect OAuth.** Live mode follows Zerodha's redirect-based auth: backend exposes `/kite/login-url`, user is redirected to `kite.zerodha.com`, returns to `/kite/callback` with a single-use `request_token`, the backend exchanges it for a daily-expiry `access_token` stored in an HTTP-only `SameSite=Lax` cookie. Rate-limited at the 3 req/s ceiling per Kite TOS via an asyncio semaphore plus 333 ms inter-call spacing. The same `/portfolio`, `/trade-history`, `/confirm-trade` endpoints serve all three modes via an `X-Finsight-Mode` header dispatcher.

**Streaming Server-Sent Events.** The Thinking Log streams Gemma's tokens to the UI as they're produced — green "LIVE" pill, blinking cursor, auto-scroll. On timeout, the stream resolves to an explicit Gemma-unavailable audit log instead of a synthesized behavioral trace.

**FIFO lot matching.** Paper trades realize P&L correctly across partial fills. The engine tracks `quantity_remaining` per row and matches SELLs against open BUYs oldest-first, splitting partial closes without splitting rows. P&L is recorded on the closing leg only to avoid double-counting.

## Impact and the path forward

The technical depth above matters only if it reaches the people who need better guardrails at the moment of action: active stock market participants, from first-time equity buyers to high-frequency retail traders. SEBI's cash-market and derivatives studies show that harmful behavior is not confined to one instrument class; F&O simply reveals the costliest edge of a broader behavioral problem. The combination of edge AI, regulatory grounding, and a UX that respects the user's intelligence makes this a tool that can run on an ordinary laptop, in multiple Indian languages, and still interrupt the next bad decision before it compounds.

A concrete five-phase distribution plan:

1. **Phase 1 (Q3 2026)**: open-source release on GitHub under MIT license, listed in awesome-edge-ai. Free for any user with a Zerodha account via the Live Kite Connect mode shipped today.
2. **Phase 2 (Q4 2026)**: browser extension build that runs alongside Zerodha Kite Web and Groww, embedding the Speed Bump in the broker's own interface.
3. **Phase 3 (Q1 2027)**: Android app (ONNX Runtime for Gemma) for the 90% of B30 users on smartphones, launching in Hindi, Telugu, Tamil, Bengali, and Marathi.
4. **Phase 4 (Q2 2027)**: broker SDK — embeddable library brokers can integrate into their own apps. Pitch to Zerodha (already SEBI-aligned on investor protection messaging), Groww, Upstox.
5. **Phase 5 (Q3 2027)**: SEBI partnership pilot in Andhra Pradesh and Odisha, focused on behaviorally risky retail activity across cash and derivatives. Official endorsement opens a path to broker-led distribution at national scale.

Gemma 4 made the technology accessible. Finsight OS makes the protection practical. Open source. MIT licensed. Free. Forever. Because behavioral guardrails shouldn't be a premium feature — they should be part of the default market experience.

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

- **Architecture diagram**: [interactive viewer](https://finsight-os-diagrams.vercel.app/#architecture) · source `docs/architecture.html`
- **Data pipeline diagram**: [interactive viewer](https://finsight-os-diagrams.vercel.app/#data-pipeline) · source `docs/data-pipeline.html`
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
