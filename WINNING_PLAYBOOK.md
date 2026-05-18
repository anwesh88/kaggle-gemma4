# Finsight OS Hackathon Playbook

This file is the current execution playbook for the Kaggle Gemma 4 Good
submission. It describes the code that is actually shipped in this repo.

## Core Proof

Finsight OS is designed to satisfy the judging criterion around real, functional
Gemma use:

- Paper and Live Kite trades are converted into a `TradingContext`.
- The context includes recent trades, open positions, realized/open P&L,
  margin use, vows, preferred language, and behavioral history.
- `backend/ai_engine.py` sends that context to Gemma 4 through Ollama.
- The Audit Trace is built from the real context plus Gemma's structured JSON
  response.
- If Gemma fails, times out, or returns invalid JSON, the UI shows an explicit
  unavailable state. It does not fabricate mock insights.

## Shipping Modes

| Mode | Source of trades | Source of prices | Gemma context |
|---|---|---|---|
| Demo | Seeded local SQLite session | Yahoo Finance | Seeded high-risk session |
| Paper | User paper trades in SQLite | Yahoo Finance | Real paper trades and margin |
| Live Kite | Zerodha account snapshot/orders | Kite + Yahoo fallback | Real broker trades, positions, holdings, P&L, margin |

## Gemma 4 Features Demonstrated

1. Structured behavioral analysis exposed through a step-by-step audit log.
2. Structured JSON output parsed with a brace-balanced extractor.
3. Multilingual nudges in English plus Hindi, Telugu, or Tamil.
4. Multimodal chart screenshot analysis through the Gemma/Ollama vision path.
5. RAG-grounded SEBI disclosure attached after successful model inference.
6. Longitudinal behavioral memory persisted locally through SQLite.
7. QLoRA fine-tuning pipeline in `finetune/` for SEBI-grounded adaptation.

## Deployment Track

Use `docs/deploy.md` as the source of truth.

- GitHub: `https://github.com/anwesh88/kaggle-gemma4`
- Frontend: Vercel, root directory `frontend`
- Backend: Railway, root directory `backend`
- Kite secrets: Railway environment variables only
- Public frontend env: `NEXT_PUBLIC_API_URL=<Railway backend URL>`

Railway CPU is acceptable for the API/paper/Kite surface, but real Gemma
inference requires an Ollama runtime reachable from the backend. For the most
reliable judging proof, run the local path with Ollama:

```powershell
ollama serve
ollama pull gemma4:e2b

cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python main.py

cd ..\frontend
npm install
npm run dev
```

## Verification Checklist

- `npm run build` passes in `frontend/`.
- Backend imports cleanly and `/health` returns 200.
- `backend/tests/test_ai_engine_real_context.py` proves paper trades and vows
  enter the Gemma prompt.
- `backend/tests/test_paper_trading_ai_context.py` proves open paper trades are
  visible to Gemma.
- `backend/tests/test_broker_client_ai_context.py` proves Live Kite positions
  and broker P&L are visible to Gemma.
- `backend/tests/test_cors.py` proves localhost dev CORS preflights pass.
- GitHub push contains no `.env`, Kite token, venv, `.next`, SQLite DB, or
  local editor state.
