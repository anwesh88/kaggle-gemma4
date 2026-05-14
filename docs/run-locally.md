# Finsight OS — Run Locally

End-to-end setup for backend (FastAPI + Ollama + Gemma 4) and frontend (Next.js 14).

Judges who want to verify real Gemma 4 inference should use the dedicated
copy-paste guide: [docs/judge-local-gemma.md](judge-local-gemma.md).

## 0. Prerequisites

| Tool | Why | Verify |
|---|---|---|
| Python 3.10+ | backend | `python --version` |
| Node 18+ | frontend | `node --version` |
| Ollama | local Gemma 4 inference | `ollama --version` (download from https://ollama.com/download) |
| Git | clone / push | `git --version` |

## 1. Pull the Gemma 4 model (one-time)

```
ollama pull gemma4:e2b
```

CPU-only laptop? Stay on `gemma4:e2b`. GPU? `ollama pull gemma4:e4b` and set `OLLAMA_MODEL=gemma4:e4b` in `backend/.env`.

Make sure the Ollama daemon is running before you start the backend. On Windows it auto-starts after install; on Linux/macOS run `ollama serve` in a separate terminal.

Both `gemma4:e2b` and `gemma4:e4b` are natively multimodal, so the Chart Analyzer reuses the same model — no separate vision pull needed.

## 2. Backend (FastAPI)

### PowerShell (Windows)

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env       # then edit if needed
uvicorn main:app --reload --port 8000
```

### Bash (macOS / Linux / WSL)

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env         # then edit if needed
uvicorn main:app --reload --port 8000
```

Backend serves at `http://localhost:8000`. Health check: `http://localhost:8000/health`.

## 3. Frontend (Next.js)

In a **second terminal**:

```
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. Pick a mode (Demo / Paper Trading / Live Kite Connect) on the selector card.

## 4. Optional — Live Kite Connect (real Zerodha account)

### 4.1 Register the app

1. Create an app at https://developers.kite.trade/apps/.
2. Set the **Redirect URL** to **exactly**:
   ```
   http://localhost:8000/kite/callback
   ```
   (`http`, port `8000`, ending in `/kite/callback`).
3. **Whitelist your public IP** in the app's **Allowed IPs** field — this is required for placing real orders. Find your IP at https://api.ipify.org. Home connections often have dynamic IPs, so re-check this if `/kite/place-order` ever rejects with `PermissionException: No IPs configured`.
4. Copy the API key + secret into `backend/.env`:
   ```
   KITE_API_KEY=your_api_key_here
   KITE_API_SECRET=your_api_secret_here
   ```

### 4.2 Mint an access token (once per IST day — tokens expire ~6 AM IST)

Either click **Login with Zerodha** on the Live Kite card (uses the registered redirect URL → backend exchanges → cookie set), or use the CLI helper if the redirect URL is misconfigured:

```
cd backend
python scripts/kite_login.py
```

The CLI prints the Zerodha URL, you log in, paste the redirected URL back. The access token is Fernet-encrypted to `backend/data/kite_access_token.encrypted` and auto-restored on the next backend startup.

Frontend also has a **"Stuck on the redirect? Use manual login"** disclosure on the Mode Selector when configured-but-unauthenticated, so you can paste the request_token from the browser bar without touching the CLI.

### 4.3 Verify

```
curl http://localhost:8000/kite/status
```

Expected: `{"configured": true, "authenticated": true, "user_name": "..."}`.

Full Kite walkthrough with screenshots: [docs/kite-setup.md](kite-setup.md).

## 5. Optional — Fine-tune the LoRA on Kaggle T4

Self-contained QLoRA pipeline against Gemma 4 E2B in 4-bit nf4.

```
cd finetune
pip install -r requirements.txt   # transformers, peft, bitsandbytes, datasets
python build_dataset.py            # SEBI + behavioral instruction set
python train.py                    # ~45 min on a single T4
python evaluate.py                 # spot-checks the adapter
```

Detailed notebook: [docs/gpu-setup.md](gpu-setup.md).

## 6. Common stop / restart cheatsheet

| Goal | Command |
|---|---|
| Stop backend | `Ctrl+C` in the uvicorn terminal |
| Stop frontend | `Ctrl+C` in the `npm run dev` terminal |
| Wipe paper-trading DB | `del backend\paper_trading_user.db` (PowerShell) or `rm backend/paper_trading_user.db` |
| Reset demo session | `POST /paper/reset` in Demo mode, or delete `backend/paper_trading_demo.db` |
| Force Ollama warmup | `ollama run gemma4:e2b "ok"` once |
| Free port 8000 / 3000 | `npx kill-port 8000 3000` |
| Re-login to Kite | `python backend/scripts/kite_login.py` |

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `503 Ollama unavailable` | daemon not running | `ollama serve` (Linux/mac) or relaunch Ollama tray app (Windows) |
| Streaming spinner never returns a score | model not pulled, or first-token cold start | confirm `ollama list` shows `gemma4:e2b`; first request takes 30–60s on CPU |
| Frontend `Failed to fetch` | backend not on :8000 or CORS mismatch | confirm `FRONTEND_URL` in `backend/.env` matches the browser URL |
| Next.js dev fails with `EINVAL: invalid argument, readlink` | OneDrive reparse-points on `.next` | Right-click `kaggle` folder → **Always keep on this device**, then `Remove-Item -Recurse -Force frontend\.next` and rerun `npm run dev` |
| Kite login lands on `https://127.0.0.1/` ERR_CONNECTION_REFUSED | redirect URL misconfigured in dev console | Set Kite app **Redirect URL** to `http://localhost:8000/kite/callback`. Or use the in-app manual-paste fallback |
| `/kite/place-order` returns `PermissionException: No IPs configured` | IP not whitelisted | Get your public IP from https://api.ipify.org, add to **Allowed IPs** on the Kite app. Home IPs rotate — re-check periodically |
| `/kite/place-order` returns "Insufficient funds" | available cash below order value | reduce quantity, switch to a cheaper symbol, or add funds |
| Chart Analyzer times out on CPU | Gemma 4 vision is slow on i7-class CPUs | Increase `OLLAMA_VISION_TIMEOUT_S` in `backend/.env`, or `ollama pull moondream` and set `OLLAMA_VISION_MODEL=moondream` |

## 8. Production / hosted demo

For GitHub + Vercel + Railway deployment, follow [docs/deploy.md](deploy.md). Kite API keys belong in the backend host's environment variables, not in Vercel's public frontend environment.
