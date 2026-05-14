# Finsight OS — Submission Day Checklist

Single-page T-minus-24h walkthrough. Don't submit until every box is ticked.

**Deadline:** May 18, 2026 (Kaggle competition close)
**Target submit time:** May 17, 2026, 18:00 IST (24 h buffer)

---

## T-7 days: content lock

- [ ] **Writeup v2** at `docs/kaggle-writeup.md` reviewed cold-read for tone, typos, length (≤1500 words by `wc -w`)
- [ ] **Three references** marked `🔗 NEEDED` in `docs/references.md` filled in with real URLs and quotes
- [ ] **Fine-tune notebook** trained on Kaggle T4 → adapter pushed to HuggingFace Hub as `finsight-os/gemma4-e2b-sebi-lora-v1`
- [ ] **Benchmark numbers** populated into `docs/finetune-results.md` (real measured table, not placeholder)
- [ ] **Face-cam delivery rehearsed** against `docs/talking-points.md` — 3 clean takes recorded against the recording-setup checklist

## T-5 days: video shoot

- [ ] **Backend pre-warmed** on dev machine, Speed Bump fires on first /analyze-behavior
- [ ] **Screen recording** of Act 2 dashboard demo, single continuous take, 1080p60
- [ ] **Optional GPU recording session** if Live Kite mode is to be shown — RunPod A4000 30 minutes (~₹15)
- [ ] **B-roll clips** from Pixabay downloaded, organized in `assets/raw/`
- [ ] **Cover image** rendered from `docs/cover-image.html` to `cover.png` at 1280×720

## T-3 days: video edit

- [ ] **DaVinci Resolve** timeline assembled per `docs/video-script.md` 3-act structure
- [ ] **Voiceover** dropped on audio bus, sidechain ducked at -28 dBFS under VO
- [ ] **Captions** auto-generated then proofread for "lakh", "crore", "Nifty", "Gemma"
- [ ] **Color grade** pass — warm highlights, lift shadows, no over-grading
- [ ] **Master loudness** at -16 LUFS, -1 dBTP ceiling
- [ ] **Export** H.264, 1080p, ~12 Mbps, AAC 192 kbps
- [ ] **Length** ≤ 3 minutes (Kaggle hard cap)

## T-2 days: deploy

- [ ] **GitHub repo** pushed, public visibility verified in incognito browser
- [ ] **README.md** renders cleanly on github.com (badges, tables, code blocks)
- [ ] **Vercel frontend** deployed — `https://finsight-os.vercel.app` opens to mode selector
- [ ] **Railway backend** deployed — `/health` responds with `{model:"gemma4:e2b", edge_ai:true}`
- [ ] **NEXT_PUBLIC_API_URL** env var on Vercel points to the Railway URL
- [ ] **CORS** allows the Vercel domain (`FRONTEND_URL` / `FRONTEND_ORIGINS` env vars on Railway)
- [ ] **YouTube upload** as **Public** (NOT Unlisted), title set, description filled
- [ ] **Chapter markers** at 0:00 (Problem), 1:00 (Demo), 2:30 (Vision)
- [ ] **All YouTube links** verified in incognito (no login required to watch)

## T-1 day: judge dry-run

- [ ] **Friend follows README** from a fresh machine — they can install + run in under 10 min
- [ ] **All four modes verified** — Demo loads, Paper accepts a BUY, Live Kite shows REQUIRES SETUP without backend config, Live Kite logs in successfully with backend config
- [ ] **Speed Bump fires** on the seeded high-risk session
- [ ] **Streaming Thinking Log** shows live tokens
- [ ] **Architecture diagram** opens at `docs/architecture.html` and renders
- [ ] **Cover image** opens at `docs/cover-image.html` and renders at 1280×720
- [ ] **Live demo URL** works in incognito
- [ ] **YouTube URL** plays without login

## T-1 day: Kaggle Writeup creation

Go to https://www.kaggle.com/competitions/gemma-4-good-hackathon/projects → **New Writeup**.

- [ ] **Title:** `Finsight OS — Behavioral Guardian for India's 9.6M Retail F&O Traders`
- [ ] **Subtitle:** `A privacy-first edge-AI Speed Bump built on Gemma 4`
- [ ] **Track:** Digital Equity & Inclusivity
- [ ] **Body:** paste markdown from `docs/kaggle-writeup.md`
- [ ] **Cover image:** upload `cover.png` (1280×720)
- [ ] **Project Links:**
  - GitHub repo URL
  - YouTube video URL
  - Live demo URL
- [ ] **Media Gallery:**
  - Video (auto-attached from YouTube)
  - Cover image
  - Architecture diagram screenshot (1200×720 export of `docs/architecture.html`)
  - Speed Bump modal screenshot (mid-cooldown, mid-typing)
  - Streaming Thinking Log screenshot (mid-stream, with cursor)
  - Mode selector screenshot
- [ ] **Save** the Writeup (top-right Save button)
- [ ] **Verify** the Writeup page shows correctly when viewed in incognito browser

## T-0: submit

- [ ] **Click Submit button** in Kaggle Writeup at top-right
- [ ] **Take screenshot** of submission confirmation
- [ ] **Verify** the entry appears at https://www.kaggle.com/competitions/gemma-4-good-hackathon/leaderboard (or the Submissions page)

If you need to update after submission:
- The Kaggle Writeup can be **un-submitted, edited, and re-submitted** unlimited times before the deadline
- The cleanest workflow: edit → Save → re-Submit
- Each Submit creates a new evaluation entry; the latest one is what's judged

---

## What can go wrong, and what to do

| Failure | Cause | Fix |
|---|---|---|
| YouTube video shows "Private — sign in" to judges | You uploaded as Unlisted, not Public | Change to Public in YouTube Studio |
| Vercel deploy returns 404 | Build failed silently | Check Vercel deployment logs; usually a missing env var |
| Hosted analysis shows Gemma unavailable | Railway CPU backend cannot reach an Ollama/Gemma runtime, or the paid GPU pod is offline | Use `docs/judge-local-gemma.md` for local verification or point `OLLAMA_HOST` at a reachable GPU/Ollama service |
| `/analyze-behavior` returns 500 | Backend startup/config issue | Check Railway logs and confirm all required backend env vars are set |
| Live Kite "Login with Zerodha" 404s | KITE_REDIRECT_URL doesn't match the registered app's URL | Step 1 of `docs/kite-setup.md` |
| Cover image attaches but renders blurry | Wrong aspect ratio uploaded | Re-export at exactly 1280×720 PNG |
| Word count > 1500 | Writeup expanded beyond limit | Trim from References section first |
| Submit button greyed out | Required field missing | Kaggle highlights it in red — usually Track or cover image |

---

## Final sanity question before clicking Submit

Read this aloud:

> "If a judge clicks the GitHub link, then the YouTube link, then the live
> demo URL, in that order, with no prior context — does each one make sense
> on its own AND together tell a coherent story about a privacy-first
> behavioral guardian for Indian retail F&O traders built on Gemma 4?"

If yes → submit. If no → fix the gap before submit.
