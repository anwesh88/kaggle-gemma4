# Live Kite Connect setup — 5-minute walkthrough for judges

Finsight OS ships with three deployment modes: **Demo**, **Paper Trading**,
and **Live Kite Connect**. The first two need no setup. This guide enables
the third, which connects the app to a real Zerodha trading account so
holdings, positions, and orders go through the actual broker API.

The integration is **fully implemented in the public repo**. This guide is
for reviewers who want to verify the broker plumbing end-to-end. The
recorded video uses Demo + Paper modes to avoid leaking authenticated
account data publicly (per Zerodha's API Terms of Service).

## Cost

**Zero.** Zerodha's "Personal" tier of Kite Connect is **₹0 / month** and
covers everything Finsight OS uses (orders, holdings, positions, profile,
margin, quotes). The ₹500/month "Connect" tier is only required for
WebSocket live ticks and historical candle data — neither of which Finsight
needs (we use Yahoo Finance for prices).

You do need an existing Zerodha trading account to log in. Opening one is
free but requires Indian KYC.

## Step 1 — Register a Kite Connect app (one-time, ~3 min)

1. Go to https://kite.trade/connect/
2. Sign in with your Zerodha credentials
3. Click **Create new app**
4. Fill the form:
   - **App name**: `Finsight OS Local`
   - **App type**: `Connect`
   - **Redirect URL**: `http://localhost:8000/kite/callback` (exactly this)
   - **Allowed IPs**: paste both your public **IPv4** and **IPv6** addresses (find them at https://www.showmyip.com/). **Required for placing real orders** — Zerodha's write API rejects calls from non-whitelisted IPs with `PermissionException: No IPs configured`. Read-only calls (holdings, quotes, positions) work without this, but `place_order` won't.
   - **Description**: `Behavioral guardian for retail F&O traders`
5. Submit. You'll see your **API key** and **API secret** on the next page.
   Copy both — the secret is shown only once.

> **Dynamic-IP heads-up:** most home broadband connections rotate public IPs after router restarts. If `/kite/place-order` ever returns `PermissionException: No IPs configured`, re-check both IPv4 and IPv6 at https://www.showmyip.com/ and re-save both on the Kite app. Read endpoints will keep working even with a stale IP whitelist.

Important:
- Use `localhost` consistently for local login.
- Do not register `127.0.0.1`, `https://127.0.0.1/`, or any HTTPS localhost variant unless you are actually serving that exact origin.
- The browser login flow in this repo is backend-callback-first. Zerodha should redirect to `http://localhost:8000/kite/callback`.

## Step 2 — Configure the backend (1 min)

Open `backend/.env` (copy from `backend/.env.example` if it doesn't exist
yet) and set:

```bash
KITE_API_KEY=your_api_key_from_step_1
KITE_API_SECRET=your_api_secret_from_step_1
KITE_REDIRECT_URL=http://localhost:8000/kite/callback
```

Make sure the `kiteconnect` + `cryptography` packages are installed in the backend venv:

```powershell
cd C:\Users\anwes\OneDrive\Desktop\kaggle\backend
venv\Scripts\activate
pip install kiteconnect cryptography
```

> `cryptography` is used to Fernet-encrypt the Kite access_token at rest
> (in `data/kite_access_token.encrypted`) so the session survives backend
> restarts. The encryption key auto-generates at `data/kite_secret.key`.
> Both files are git-ignored.

## Step 3 — Start the backend (30 sec)

```powershell
$env:DEMO_MODE="true"
python main.py
```

In the startup logs you'll see:

```
Finsight OS - Behavioral Guardian for India's Retail Traders
   Mode: DEMO (Seeded high-risk session)
   AI:   gemma4:e4b via Ollama (local, private, CPU)
   RAG:  SEBI circulars indexed
```

Verify Kite is recognized:

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/kite/status"
```

Expected:

```
configured     : True
authenticated  : False
```

## Step 4 — Pick the mode in the UI (10 sec)

1. Open http://localhost:3000 in your browser
2. The mode selector appears as the first screen
3. The **Live Kite Connect** card now shows "REAL BROKER" badge (green)
   instead of "REQUIRES SETUP"
4. Click **Login with Zerodha**

## Step 5 — Log in via Zerodha's OAuth (30 sec)

1. The browser redirects to `https://kite.zerodha.com/connect/login?…`
2. Enter your Zerodha credentials + complete 2FA
3. Zerodha redirects back to `http://localhost:8000/kite/callback?...`
4. Finsight's backend exchanges the request_token for an access_token,
   sets an HTTP-only session cookie, then redirects the browser to the
   frontend callback page so Live Kite mode is persisted automatically
5. Header now shows the **LIVE** badge instead of DEMO; the Live Kite Connect
   pill is green; your Zerodha user name appears in the corner

## Step 6 — Verify the integration (30 sec)

In the dashboard, with mode = Live Kite:

- **Today's Trades** panel pulls from Kite's `/trades` endpoint (real fills
  from your account, normalized into one broker snapshot)
- **Margin Usage** panel pulls from Kite's live broker snapshot, not the
  paper-trading SQLite model
- **Holdings / Watchlist / Positions** all render from the same broker snapshot
- **Place Order** uses Kite's `/orders` API — actually submits a real order
  on Zerodha. **The Mindful Speed Bump still gates this** — the order is
  only sent after the commitment phrase is typed AND the cooldown elapses.

To verify without placing a real trade, click the API docs:
`http://localhost:8000/docs` → `/portfolio` → Try it out → Execute. You
should see your actual Zerodha holdings and positions in the response.

## Alternative: CLI login flow (no browser callback needed)

If you're running Finsight OS in Docker, on a headless server, or just
prefer the command line, use the CLI script instead of the web flow:

```powershell
cd backend
venv\Scripts\activate
python scripts\kite_login.py
```

The script:
1. Prints your Zerodha login URL — open it in any browser
2. Complete login on Zerodha's site
3. After Zerodha redirects you, copy the `request_token` query parameter
   from the URL (e.g. `?request_token=ABC123&action=login&status=success`)
4. Paste it back at the prompt
5. The script exchanges + encrypts + saves the token

Restart the backend (`python main.py`) and the session auto-restores —
you'll see `Kite: Restored session for <your_name>` in the startup log.

This is the same pattern as anwesh's reference `login_fixed.py`.

## Daily token expiry

Kite Connect access tokens expire at **6:00 AM IST** every day. After that,
the next API call returns 401, the session cookie is cleared automatically,
the encrypted disk copy is wiped, and the UI prompts re-login. This is
Zerodha's design, not ours.

On backend startup, `restore_session_from_disk()` test-validates the saved
token via `KiteConnect.profile()` before trusting it — if 6 AM IST passed
while the server was down, the stale token is detected and cleared
automatically.

## Common errors

| Error | Cause | Fix |
|---|---|---|
| `503 Kite Connect is not configured` | `.env` values missing | Step 2 |
| `Invalid `redirect_url`` from Zerodha | Mismatch between the redirect on kite.trade and `KITE_REDIRECT_URL` | Make them identical, no trailing slash |
| `kiteconnect package not installed` | venv missing the lib | `pip install kiteconnect cryptography` in backend venv |
| `cryptography package not installed` | encrypted-token persistence needs Fernet | `pip install cryptography` |
| Backend says `Restored session for None` | profile JSON sidecar got corrupted | wipe `data/kite_*.json` and re-OAuth once |
| `401 Kite access_token expired` | Daily 6 AM IST expiry | Click logout → login again |
| Login redirects to a 404 | Backend not running on `:8000` | Start backend before clicking login |
