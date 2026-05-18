# Finsight OS · GPU Deployment Guide

This document covers running the Finsight OS backend on a cloud GPU instance
so real Gemma 4 inference completes in under 10 seconds (vs. 60-90 s on a
4-year-old CPU laptop).

The codebase ships **GPU-ready by default** — every Ollama option is
override-able via environment variable. No code changes needed; only env
configuration.

## Why this matters

Real Gemma 4 E4B inference can exceed the timeout on a four-year-old
i7-1255U / 16 GB laptop in our development environment. On timeout, the
app now shows an explicit "Gemma unavailable" state instead of a
representative behavioral response. On any GPU instance with 16+ GB VRAM,
the full inference pipeline returns in under 10 seconds. This guide is for:

- Recording the submission video with real Gemma streaming visible
- Hosting the live demo for judges to verify
- Production deployment for actual users (B30 trader on the receiving end
  benefits from a centralized GPU host with edge-AI privacy guarantees still
  preserved via session isolation)

## The single config that switches CPU → GPU

Set these environment variables before starting `python main.py`:

```bash
export OLLAMA_NUM_GPU=99             # offload all layers to GPU
export OLLAMA_NUM_CTX=2048           # bigger context window
export OLLAMA_NUM_PREDICT=400        # full thinking_log + JSON
export OLLAMA_KEEP_ALIVE=30m         # keep model loaded between requests
export OLLAMA_TIMEOUT_S=30           # GPU finishes in <10s; 30s is safe
```

That's it. The rest of the code is unchanged. The `/health` endpoint will
print `(GPU)` instead of `(CPU)` in the inference logs.

## Option A · Kaggle free GPU notebook

Best for: video recording session.

1. Create a new Kaggle notebook
2. Settings → Accelerator → **GPU T4 x1** (free, 30h/week limit)
3. Install Ollama in the notebook:
   ```bash
   !curl -fsSL https://ollama.com/install.sh | sh
   !nohup ollama serve > /tmp/ollama.log 2>&1 &
   !sleep 3 && ollama pull gemma4:e2b
   ```
4. Clone the Finsight backend, install deps, run with the GPU env vars above.
5. Ngrok the FastAPI port so your local frontend can hit it:
   ```bash
   !pip install pyngrok
   !ngrok http 8000
   ```

## Option B · RunPod (~$0.30/hr for A4000)

Best for: short recording sessions where you want guaranteed VRAM and zero
queue time.

1. Create RunPod account, add $5 credit
2. Deploy → Pods → A4000 16 GB (cheapest viable) or RTX 4090 24 GB
3. Template: `runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04`
4. SSH into the pod, install Ollama + dependencies (same as above)
5. Expose port 8000 via RunPod's HTTP proxy
6. Total cost for a 30-minute video shoot: ~$0.15

## Option C · Modal (serverless, scale-to-zero)

Best for: hosting the live demo for judges. Pay only when judges actually
hit the endpoint.

```python
import modal

app = modal.App("finsight-os")
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("curl")
    .run_commands("curl -fsSL https://ollama.com/install.sh | sh")
    .pip_install("fastapi[standard]", "ollama", "yfinance", "chromadb",
                 "pydantic", "python-dotenv", "uvicorn", "python-multipart")
    .add_local_dir("backend", "/root/backend")
)

@app.function(image=image, gpu="A10G", timeout=600,
              container_idle_timeout=300, allow_concurrent_inputs=10)
@modal.asgi_app()
def fastapi_app():
    import subprocess, time, os
    subprocess.Popen(["ollama", "serve"])
    time.sleep(3)
    subprocess.run(["ollama", "pull", "gemma4:e2b"], check=True)
    os.environ["OLLAMA_NUM_GPU"] = "99"
    os.environ["OLLAMA_NUM_CTX"] = "2048"
    os.environ["OLLAMA_KEEP_ALIVE"] = "30m"
    from backend.main import app as fastapi_app
    return fastapi_app
```

Deploy with `modal deploy modal_app.py`. Scales to zero when idle, A10G GPU
runs at ~$1.10/hr only while serving requests.

## Option D · Colab Pro ($10/month)

Best for: testing the LoRA adapter (see `finetune/README.md`) AND running
the backend in the same notebook for short recording sessions.

Same setup as Kaggle but with longer session limits.

## Verifying real GPU inference is happening

After starting the backend with GPU env vars, watch for these signals:

In the backend console:
```
[Finsight AI] Running gemma4:e2b locally (GPU)...
[Finsight AI] Inference: 4.82s (412 chars)        ← under 10s = GPU
```

In the response JSON:
```json
{
  "inference_seconds": 4.82,                       ← real completed inference
  "behavioral_score": 847,                         ← varies, not exactly 892
  ...
}
```

In the UI badge in the dashboard:
- Green "▮ Gemma 4 · e2b · 4.8s · local" pill for completed inference

## Cost summary

| Use case | Recommended | Cost |
|---|---|---|
| One-time video recording (30 min) | RunPod A4000 spot | ~$0.15 |
| Hosting live demo for judges | Modal A10G serverless | ~$0.50 / day idle, scales with usage |
| Fine-tune training (~2h on T4) | Kaggle free GPU | ₹0 |
| Continuous production | Modal A10G or self-hosted RTX 3090 | ~$50/mo or one-time hardware |

For the May 18 submission, the practical path is **RunPod for one recording
session** + **Modal for the live demo URL** = total budget under $5.

## Privacy preserved when using cloud GPU

The strict on-device privacy story only applies to the local deployment:
behavioral features, scores, nudges, and memory remain on the user's hardware,
while public quote lookups and optional broker calls follow their documented
external paths. When deployed on Modal/RunPod for the hosted demo, behavioral
analysis is processed on the cloud GPU instance instead.

The writeup should clearly state that the **shipped product is the local
edge-AI version**; the hosted demo is a convenience for judges to evaluate
without installing anything. The actual production-recommended deployment
is the user's own laptop or phone, exactly as described in the architecture
diagram.

## Verifying the GPU env vars are being honored

Quick sanity check:

```bash
$ curl http://localhost:8000/health
{"status":"ok","demo_mode":true,"model":"gemma4:e2b","edge_ai":true}

# Hit /analyze-behavior once and look at:
$ curl -X POST http://localhost:8000/analyze-behavior \
       -H "Content-Type: application/json" -d '{}' \
       | jq '.inference_seconds'
4.82          # ← under 10 = GPU is being used
```

If `inference_seconds` is over 30 even on a GPU instance, double-check
`OLLAMA_NUM_GPU=99` and `nvidia-smi` to confirm the model is actually loaded
into VRAM. Sometimes Ollama needs an explicit pull-and-warm cycle:

```bash
ollama pull gemma4:e2b
ollama run gemma4:e2b "hi"        # forces full GPU load
```
