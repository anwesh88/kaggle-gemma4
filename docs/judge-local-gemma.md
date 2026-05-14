# Judge Guide: Verify Real Gemma Locally

The hosted Vercel + Railway demo is available for quick UI review, but the
cloud GPU runtime for Gemma may be offline during judging because keeping a
GPU pod running continuously costs money. Finsight OS does not replace missing
model output with mock insights. If Railway cannot reach Ollama, the UI shows
`Gemma unavailable`.

Use this local path to verify that the Gemma 4 pipeline is real and functional.

## What This Proves

- Trades placed in Paper mode are sent to the backend.
- The backend injects trades, vows, portfolio state, behavioral history, and
  SEBI RAG context into the Gemma prompt.
- Gemma returns structured behavioral analysis.
- The Thinking Log and Finsight Intelligence panel display model-derived output,
  not hardcoded demo text.

## 1. Install Prerequisites

Install:

- Python 3.10 or newer
- Node.js 18 or newer
- Git
- Ollama from https://ollama.com/download

Verify:

```bash
python --version
node --version
git --version
ollama --version
```

## 2. Start Gemma 4 With Ollama

In Terminal 1:

```bash
ollama pull gemma4:e2b
ollama serve
```

If Ollama says the server is already running, leave it running and continue.

Verify:

```bash
curl http://localhost:11434/api/tags
```

Expected: JSON containing `gemma4:e2b`.

## 3. Run The Backend

In Terminal 2:

### Windows PowerShell

```powershell
git clone https://github.com/anwesh88/kaggle-gemma4.git
cd kaggle-gemma4\backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --reload --port 8000
```

### macOS / Linux / WSL

```bash
git clone https://github.com/anwesh88/kaggle-gemma4.git
cd kaggle-gemma4/backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --port 8000
```

Verify:

```bash
curl http://localhost:8000/health
```

Expected: JSON with `status` set to `ok` and `model` set to `gemma4:e2b`.

## 4. Run The Frontend

In Terminal 3:

```bash
cd kaggle-gemma4/frontend
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

Choose **Paper Trading**.

## 5. Verify Real Gemma Analysis

1. Search for a symbol such as `RELIANCE`.
2. Place a paper BUY trade.
3. Confirm it appears in **Today's Trades**.
4. Wait for the **Gemma Thinking Log**.
5. Confirm the log mentions actual trade counts and vows.
6. Confirm the **Finsight Intelligence** panel updates from model output.

You can also call the backend directly:

```bash
curl -X POST http://localhost:8000/analyze-behavior \
  -H "Content-Type: application/json" \
  -H "X-Finsight-Mode: paper" \
  -d "{}"
```

Expected: JSON containing fields such as `behavioral_score`, `risk_level`,
`detected_pattern`, `vows_violated`, `nudge_message`, and `inference_seconds`.

On CPU-only machines, inference may take 60-120 seconds. If the timeout is hit,
the app will explicitly report `Gemma unavailable` rather than inventing a
score. On a local GPU, set `OLLAMA_NUM_GPU=99` in `backend/.env` for faster
inference.

## 6. Optional Live Kite Verification

Live Kite mode requires the judge's own Zerodha/Kite API key and secret. Follow:

```text
docs/kite-setup.md
```

Kite secrets stay in `backend/.env`; they are never put in Vercel.

## Hosted Demo Note

The public hosted app demonstrates the deployed product surface:

```text
https://kaggle-gemma4.vercel.app
```

The backend is hosted on Railway, but Railway CPU hosting does not run Gemma 4
itself. Real hosted Gemma requires an external Ollama/GPU runtime configured via
`OLLAMA_HOST`. If that GPU runtime is offline for budget reasons, the local
steps above are the intended verification path.
