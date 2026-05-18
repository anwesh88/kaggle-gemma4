# Finsight OS

> A privacy-first behavioral guardian for self-directed stock market participants, built on Gemma 4.

[![Made for Kaggle Gemma 4 Good Hackathon](https://img.shields.io/badge/Kaggle-Gemma%204%20Good%20Hackathon-orange)](https://www.kaggle.com/competitions/gemma-4-good-hackathon)
[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg)](LICENSE)
[![Edge AI](https://img.shields.io/badge/Edge%20AI-100%25%20local-green)]()
[![Free tier broker](https://img.shields.io/badge/Live%20Kite%20Connect-%E2%82%B90%2Fmonth-success)]()

SEBI's FY2024-25 study found 9.6 million Indian retail traders lost a combined **₹1,05,603 crore** on equity derivatives in a single year. **91%** of them lost money. The trading apps they use were optimized to maximize trade volume, not to protect users from themselves.

**Finsight OS** maintains a local behavioral view of the current session — recent trades, trading vows, and patterns such as Revenge Trading, FOMO, and Over-Leveraging — and can place a *Mindful Speed Bump* in front of a high-risk order: a 6-18 second cognitive interrupt that requires the trader to type a 15-word commitment phrase before confirmation unlocks. Trades still happen. The user remains in control. But the impulse path now has a speed bump in it.

Behavioral intelligence runs locally by default. Public quote lookups are inbound-only, and optional Live Kite mode uses user-authorized broker calls without exporting Finsight's behavioral scores, nudges, or longitudinal profile. Speaks English, Hindi, Telugu, Tamil. Runs on a four-year-old laptop.

---

## Three modes ship today

| Mode | Setup | What you get | Best for |
|---|---|---|---|
| **Demo** | Zero | Pre-loaded high-risk session, Speed Bump fires immediately | A 30-second tour |
| **Paper Trading** | Zero | Real Yahoo prices, real SQLite paper trades, FIFO P&L | Free practice without a broker |
| **Live Kite Connect** | 5 min, ₹0 | Real Zerodha account integration via OAuth | Anyone with a Zerodha account |

---

## Quick start (local)

```powershell
# Backend
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
$env:DEMO_MODE="true"
python main.py

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) → pick a mode → start exploring.

For Live Kite Connect, follow [`docs/kite-setup.md`](docs/kite-setup.md) (5 minutes, free).

For GitHub + Vercel + Railway deployment, follow [`docs/deploy.md`](docs/deploy.md). For GPU-backed Gemma, see [`docs/gpu-setup.md`](docs/gpu-setup.md).

---

## What the demo shows

Open the dashboard and you'll see seven things working at once:

1. **Live NSE Watchlist** — real prices polled from Yahoo every 30 s, with IST market-state badge ("NSE live · updated 14:32" / "Market closed" / "Weekend")
2. **Today's Trades** — real paper trades persisted to SQLite with FIFO matching, P&L rendered per closing leg, "open" badges on in-flight positions
3. **Margin Usage** — derived from open paper positions, color-coded green/amber/red based on usage
4. **Trading Vows** — user's pre-committed identity contract, editable, fed into Gemma's prompt every analysis
5. **Finsight Intelligence** — behavioral score 0-1000, risk level, pattern, commitment phrase in EN + local language, vow violations, SEBI disclosure
6. **Streaming Audit Trace** — a 7-step evidence trail streams to the UI via SSE, each step clickable to drill into evidence
7. **Mindful Speed Bump** — modal triggered on high-risk BUY/SELL with countdown ring, exact-match phrase typing, dynamic cooldown by pattern

---

## Architecture

![Finsight OS architecture](docs/architecture.html)

Behavioral intelligence stays on the user's device. Public Yahoo Finance quotes are inbound-only, and optional Live Kite mode adds user-authorized broker traffic without exporting Finsight's behavioral scores, nudges, or longitudinal profile.

| Layer | Components |
|---|---|
| **Frontend** | Next.js 14 (App Router), TypeScript, inline-CSS theme, DM Sans, Server-Sent Events client |
| **API** | FastAPI + Uvicorn, 12 endpoints, mode-aware dispatcher |
| **Engines** | Gemma 4 via Ollama, ChromaDB SEBI RAG, paper-trading SQLite, behavioral DNA SQLite, multimodal vision, Live Kite Connect adapter |

Open [`docs/architecture.html`](docs/architecture.html) for the system view and [`docs/data-pipeline.html`](docs/data-pipeline.html) for the end-to-end data flow.

---

## Seven Gemma 4 features in use

1. **Auditable analysis trace** — a 7-step evidence trail assembled from real context plus Gemma's structured output
2. **Multimodal Vision** — chart screenshot → behavioral warning
3. **Multi-language Generation** — nudges in EN / HI / TE / TA
4. **Structured JSON Output** — strict schema, brace-balanced extraction
5. **RAG-grounded Responses** — ChromaDB SEBI corpus enriches every nudge
6. **Longitudinal Context** — SQLite behavioral DNA injected into prompt
7. **Domain adaptation via QLoRA** — see [`finetune/`](finetune/README.md) for the rank-16 LoRA pipeline trained on a SEBI-grounded instruction dataset, runnable on a free Kaggle T4 GPU in ~2 hours

---

## Documentation

| Doc | Purpose |
|---|---|
| [`docs/run-locally.md`](docs/run-locally.md) | End-to-end local setup (backend + frontend + Kite + troubleshooting) |
| [`docs/judge-local-gemma.md`](docs/judge-local-gemma.md) | Copy-paste judge path to verify real Gemma 4 inference locally |
| [`docs/model-attribution.md`](docs/model-attribution.md) | Gemma model variant naming, trademark attribution, and non-affiliation notes |
| [`docs/kaggle-writeup.md`](docs/kaggle-writeup.md) | Kaggle submission writeup (1500 words) |
| [`docs/architecture.html`](docs/architecture.html) | System architecture diagram (open in browser) |
| [`docs/data-pipeline.html`](docs/data-pipeline.html) | End-to-end data pipeline diagram |
| [`docs/cover-image.html`](docs/cover-image.html) | 1280×720 submission cover image |
| [`docs/kite-setup.md`](docs/kite-setup.md) | 5-minute Live Kite Connect walkthrough |
| [`docs/deploy.md`](docs/deploy.md) | GitHub + Vercel + Railway deployment guide |
| [`docs/gpu-setup.md`](docs/gpu-setup.md) | Cloud GPU deployment recipes (Kaggle / RunPod / Modal / Colab) |
| [`docs/video-script.md`](docs/video-script.md) | 3-minute face-cam + screen-recording shot list |
| [`docs/recording-setup.md`](docs/recording-setup.md) | Equipment + lighting + audio for the face-cam demo |
| [`docs/talking-points.md`](docs/talking-points.md) | Teleprompter beats for the face-cam delivery |
| [`docs/references.md`](docs/references.md) | Behavioral finance + SEBI bibliography |
| [`docs/finetune-results.md`](docs/finetune-results.md) | Fine-tune benchmark table (base vs. LoRA) |
| [`finetune/README.md`](finetune/README.md) | LoRA training pipeline overview |

---

## Tech stack

- **Frontend** — Next.js 14, React 18, TypeScript 5, inline-CSS (no Tailwind compile step), DM Sans font, native EventSource fallback via fetch+ReadableStream for SSE
- **Backend** — Python 3.10+, FastAPI, Pydantic v2, SQLAlchemy, ChromaDB, httpx, yfinance, kiteconnect (optional)
- **AI** — Gemma 4 (E2B / E4B) via Ollama, ChromaDB embeddings for SEBI RAG, optional QLoRA adapter via PEFT + bitsandbytes
- **Storage** — SQLite (paper trading + behavioral DNA), ChromaDB (RAG vectors), all on local disk
- **Deployment** — Vercel frontend + Railway backend; local CPU by default; GPU-ready via env vars

---

## Performance

| Hardware | Real Gemma E2B inference | UX experience |
|---|---|---|
| i7-1255U / 16 GB CPU (dev) | ~60-90 s | Real inference if completed; explicit unavailable state on timeout |
| Free Kaggle T4 GPU | ~5-8 s | Real inference visible |
| RunPod A4000 (~$0.30/hr) | ~3-5 s | Real inference fast |
| Modal A10G serverless | ~4-7 s | Real inference at scale |

The full inference pipeline — prompt construction, Ollama call, JSON parsing, RAG enrichment, behavioral DNA persistence, SSE streaming — runs on every request regardless of hardware. Paper and live Kite insights are never stubbed: if Gemma times out or returns invalid JSON, the UI shows an explicit "Gemma unavailable" state instead of a behavioral score or pattern. Override `OLLAMA_NUM_GPU=99` for faster local inference.

---

## Privacy commitment

The "no behavioral data leaves the device" claim is enforced by the architecture, not by policy:

- Gemma 4 runs at `localhost:11434` via Ollama
- All trades persist to SQLite at `backend/data/paper_trading.db` on local disk
- Behavioral DNA persists to `backend/data/behavioral_dna.db` on local disk
- ChromaDB RAG vectors live at `backend/data/chroma_db/`
- Yahoo Finance provides inbound public NSE data only; no behavioral profile is sent there
- Live Kite Connect mode adds user-authorized calls to `api.kite.trade` for broker functions, but Finsight's behavioral scores, nudges, and Behavioral DNA remain local

Network audit: run `pip install pip-audit` then `pip-audit` to verify dependency provenance.

---

## License

[CC BY 4.0](LICENSE) — unless otherwise noted, all original material in this repository is licensed under the Creative Commons Attribution 4.0 International License.

Third-party dependencies, datasets, trademarks, and Gemma model weights remain under their respective terms and are not relicensed by this repository.

## Attribution

- Gemma is a trademark of Google LLC.
- Finsight OS is an independent project and is not affiliated with or endorsed by Google.
- **Gemma 4** model family by Google DeepMind
- **Ollama** by the Ollama team
- **kiteconnect** by Zerodha Tech
- **Yahoo Finance** via `yfinance` by Ran Aroussi
- **ChromaDB** by Chroma
- **DM Sans** by Indian Type Foundry
- SEBI data from the [Securities and Exchange Board of India](https://www.sebi.gov.in/) FY2024-25 F&O Study

## Contact

Built by [@anweshmohanty](https://github.com/anweshmohanty) for the [Kaggle Gemma 4 Good Hackathon](https://www.kaggle.com/competitions/gemma-4-good-hackathon), May 2026.

If you're at SEBI, Zerodha, or any institution working on retail investor protection in India, this is open source — let's talk about a pilot. Email: anweshmohanty69@gmail.com
