# For Kaggle judges

> **TL;DR** — three ways to try Finsight OS, sized to how much time you
> have. The hosted live demo is the fastest path; one-command Docker is
> the next; native install is for deep code review.

---

## Path A — 30 seconds: hosted live demo

Open: **https://kaggle-gemma4.vercel.app**

You'll see a mode picker. Click **Demo Mode** → you land on the dashboard
with a high-risk session pre-loaded → click **BUY** on any instrument →
the **Mindful Speed Bump** modal fires with a countdown ring, a 15-word
commitment phrase, and a typing input. That's the core mechanic in 30
seconds.

What's running behind the URL: Next.js on Vercel and FastAPI on Railway.
Real NSE prices come from Yahoo and paper trades persist through SQLite. If
the Railway backend can reach an Ollama/Gemma runtime, the Thinking Log shows
real Gemma inference. If the paid GPU/Ollama runtime is offline, the UI shows
an explicit "Gemma unavailable" state rather than fake insight. To verify real
Gemma execution without relying on paid cloud GPU uptime, use
[`docs/judge-local-gemma.md`](docs/judge-local-gemma.md).

If you want to verify the integration with a real Zerodha account, follow
**Path C** below — the live demo intentionally does not expose Live Kite
Connect unless the Railway backend has the judge's Kite API key/secret and the
Kite app redirect URL is set to the Railway `/kite/callback` URL.

---

## Path B — 5 minutes: one-command Docker

If you have Docker Desktop or Docker Engine installed:

```bash
git clone https://github.com/anwesh88/kaggle-gemma4.git
cd kaggle-gemma4
cp backend/.env.example backend/.env
docker compose up
```

First build pulls Gemma 4 E2B weights (~2.5 GB), so allow ~5 minutes on a
warm broadband connection. After that, open **http://localhost:3000**.

What you get vs. Path A:
- Same three modes (Demo / Paper Trading / Live Kite Connect)
- Live Kite mode now works if you populate `KITE_API_KEY` in
  `backend/.env` per `docs/kite-setup.md`
- Inference runs on your machine — CPU by default (~60-90 s, explicit
  unavailable state on timeout), or GPU if you uncomment the `deploy` block in
  `docker-compose.yml` and have `nvidia-container-toolkit`

To shut down: `Ctrl+C` then `docker compose down`. To wipe state:
`docker compose down -v`.

---

## Path C — 10 minutes: native install (for deep code review)

```powershell
git clone https://github.com/anwesh88/kaggle-gemma4.git
cd kaggle-gemma4

# Backend
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
$env:DEMO_MODE="true"
python main.py

# Frontend (new terminal)
cd ..\frontend
npm install
npm run dev
```

Plus install Ollama and pull the model:

```powershell
# from https://ollama.com/download/windows
ollama pull gemma4:e2b
```

Then open **http://localhost:3000**.

This is the path for inspecting the code as you exercise it. Set
breakpoints, edit the prompt, swap models — it's all local.

---

## What to look for in each mode

### Demo Mode
The seeded high-risk session — 4 closed losing trades + 1 winning trade +
2 open BUY positions adding to ~85% margin usage. The behavioral score
will read 892, pattern "Revenge Trading", risk "high". Click BUY on any
instrument to see the Speed Bump fire.

### Paper Trading Mode
Real NSE prices via Yahoo Finance. The seeded trades are still there but
you can place fresh BUY/SELL orders against live prices. Trades persist
to `backend/data/paper_trading.db` with FIFO lot matching. Place a BUY of
say 5 RELIANCE — it appears in *Today's Trades* immediately, the margin
panel updates, and the next analysis incorporates it.

### Live Kite Connect Mode
Requires Zerodha account + free Kite Connect Personal tier (₹0/month).
Walkthrough: `docs/kite-setup.md`. Fully implemented; intentionally
disabled on the hosted live demo for TOS compliance.

---

## "Is this real or faked?" — verification commands

Run these to confirm the system is actually doing what the writeup claims:

```powershell
# 1. Real NSE prices via Yahoo (not random walk)
Invoke-RestMethod -Uri "http://localhost:8000/market-quotes" |
    ConvertTo-Json -Depth 4
# Expect: source="yahoo", 7 quotes, prices match Google Finance ±a tick

# 2. Real paper trades via SQLite (not in-memory)
Invoke-RestMethod -Uri "http://localhost:8000/trade-history" |
    Select -ExpandProperty trades | Select -First 3
# Expect: order_id like "ORD20260429-000001", real timestamps, real P&L

# 3. Real RAG retrieval from ChromaDB (not hallucinated)
Invoke-RestMethod -Uri "http://localhost:8000/analyze-behavior" -Method Post `
    -ContentType "application/json" -Body "{}" |
    Select -ExpandProperty sebi_disclosure
# Expect: text starting with "SEBI FY2024-25 study..." with real circular IDs

# 4. Real Gemma inference timing
Invoke-RestMethod -Uri "http://localhost:8000/analyze-behavior" -Method Post `
    -ContentType "application/json" -Body "{}" |
    Select inference_seconds, behavioral_score
# Expect on GPU: inference_seconds in 5-15 range, score varies (NOT 892)
# Expect on CPU: inference_seconds in the real runtime range if Gemma completes;
# if it times out, detected_pattern="Gemma unavailable" and no score is claimed
```

---

## On CPU timeouts (complete honesty)

Real Gemma 4 inference exceeds 90 seconds on a 4-year-old i7-1255U /
16 GB CPU laptop (the development hardware). When the timeout fires, the
app now returns an explicit `detected_pattern="Gemma unavailable"` state
with `inference_seconds=null`. It does not invent a behavioral score,
pattern, vow violation, or commitment phrase.

**The full inference pipeline is real and runs on every request** —
prompt construction, Ollama call, JSON parsing, RAG enrichment, behavioral
DNA persistence, SSE streaming. Paper and live Kite modes only show
Finsight Intelligence insights when Gemma returns parseable JSON.

On a GPU instance (Path A live demo, or Path B with `OLLAMA_NUM_GPU=99`,
or any judge running on hardware better than i7-1255U), real Gemma
reasoning is visible immediately. See `docs/gpu-setup.md` for the env
vars that switch CPU → GPU.

This is documented in the writeup's *Engineering challenges* section —
not hidden.

---

## Source-of-truth file map

If you want to verify a specific writeup claim, here's where the code is:

| Writeup claim | File |
|---|---|
| Mindful Speed Bump | `frontend/src/components/TradePanel.tsx` (modal) + `computeCooldown()` |
| Streaming Thinking Log | `backend/ai_engine.py:analyze_behavior_stream` + `frontend/src/hooks/useStreamingAnalysis.ts` |
| FIFO lot matching | `backend/paper_trading.py:record_trade` |
| Yahoo Finance prices | `backend/market_data.py` |
| ChromaDB SEBI RAG | `backend/rag_engine.py` |
| Behavioral DNA | `backend/behavioral_dna.py` |
| Three-mode dispatcher | `backend/main.py:get_mode` + `frontend/src/lib/mode.ts` |
| Live Kite Connect | `backend/kite_client.py` + `/kite/*` routes in `main.py` |
| LoRA fine-tune | `finetune/{train,evaluate,build_dataset}.py` |
| GPU env-var overrides | `backend/ai_engine.py:OLLAMA_OPTIONS` |
| Architecture diagram | `docs/architecture.html` (open in browser) |

---

## If something breaks

Most common issues, in descending frequency:

1. **`ollama: command not found`** — install Ollama from
   https://ollama.com/download (Windows / Mac / Linux installers)
2. **Frontend builds but `/analyze-behavior` returns 500** — Ollama isn't
   running. Start it: `ollama serve` in another terminal.
3. **`/market-quotes` returns `source: "fallback"`** — Yahoo Finance hit a
   rate limit or your network blocks it. Wait 30 s; the cache will retry.
4. **`/health` works but the dashboard is blank** — the frontend env var
   `NEXT_PUBLIC_API_URL` doesn't match the backend. Check
   `frontend/.env.local`.
5. **Live Kite shows "Backend not configured"** — set `KITE_API_KEY` and
   `KITE_API_SECRET` in `backend/.env` per `docs/kite-setup.md`.

If something else breaks, please open a GitHub issue with the error
message and the OS — we'll fix and credit you in the next release.

---

## Contact

Submission by Anwesh Mohanty for the Kaggle Gemma 4 Good Hackathon, May
2026. Email: anweshmohanty69@gmail.com · GitHub: @anwesh88.

If you're at SEBI, Zerodha, or any institution working on retail investor
protection in India, see `docs/pilot-pitch.md` for a one-page proposal
for a 6-month observational pilot in Andhra Pradesh and Odisha.
