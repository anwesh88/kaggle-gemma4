# Finsight Guardian SEBI LoRA - adapter for Gemma 4 E2B

A small, reproducible adapter that improves Gemma 4 E2B's accuracy on
SEBI-grounded behavioral analysis for Indian retail F&O traders. Trained
with QLoRA in ~2 hours on a single T4 GPU (free on Kaggle / Colab).

Naming note: the external adapter uses the distinct model name
`finsight-guardian-sebi-lora-v1`. Gemma is referenced only as the base model
family in descriptions and attribution.

## Why this exists

The Kaggle Gemma 4 Good Hackathon brief explicitly asks:
> "We want to see how you enhance Gemma 4 models through **post-training,
> domain adaptation**, and agentic retrieval to ensure accurate, grounded
> outputs."

The base Gemma 4 E2B model produces reasonable behavioral analyses but
hallucinates SEBI circular numbers and gets Indian financial pronunciation
wrong in nudges. This adapter tightens both: regulatory citations come from
the real corpus, nudges read like a Mumbai investor advisor, and the JSON
output schema is followed more reliably.

## What you get

After training:
- A ~50 MB `adapter_model.safetensors` LoRA adapter
- Pushed to HuggingFace Hub as `finsight-os/finsight-guardian-sebi-lora-v1`
- Loadable in two ways:
  - `peft.PeftModel.from_pretrained(...)` — for HuggingFace transformers
  - `ollama create -f Modelfile-sebi` — for the Ollama runtime (after
    merging weights, see `docs/finetune-results.md`)
- Benchmark numbers: regulatory-citation accuracy, JSON-schema compliance,
  Hindi-translation BLEU — all measured against the held-out test set

## Quick start (Kaggle, free T4)

1. Upload this directory to a new Kaggle notebook.
2. Enable GPU: Settings → Accelerator → GPU T4 x1.
3. Run:
   ```bash
   pip install -q -U "transformers>=4.45" "peft>=0.13" "bitsandbytes>=0.44" \
                     "accelerate>=0.34" "datasets>=3.0" "trl>=0.11" "safetensors"
   python build_dataset.py --out data/sebi_train.jsonl
   python train.py --dataset data/sebi_train.jsonl --output adapters/v1
   python evaluate.py --adapter adapters/v1 --test data/sebi_test.jsonl
   ```
4. Training time: ~90-120 minutes on T4, ~30 minutes on A100.

## Quick start (Colab, free T4)

Same as Kaggle. Mount Drive if you want adapter persistence:

```python
from google.colab import drive
drive.mount('/content/drive')
!python train.py --dataset data/sebi_train.jsonl \
                 --output /content/drive/MyDrive/finsight/adapters/v1
```

## Quick start (RunPod / Modal / paid GPU)

A100 / H100 cuts training to 15-25 minutes. Same scripts, same flags. Use
`--per-device-batch-size 8 --grad-accum 2` to consume the larger memory.

## Files

| File | Purpose |
|---|---|
| `build_dataset.py` | Synthesizes 250+ instruction-response pairs from the 5 SEBI seed docs. Output: `data/sebi_train.jsonl` + `data/sebi_test.jsonl` (90/10 split). |
| `train.py` | QLoRA training. 4-bit base + rank-16 adapter on attention projections (q,k,v,o). Cosine LR schedule, ~3 epochs. |
| `evaluate.py` | Side-by-side eval: base model vs. adapter on regulatory-citation accuracy, JSON validity, structured-output schema compliance. Prints a markdown table. |
| `seed_examples.jsonl` | 30 hand-written gold examples that anchor the synthesis. Reviewed for SEBI accuracy. |
| `README.md` | This file. |

## Hyperparameters

```python
LoraConfig(
    r=16, lora_alpha=32, lora_dropout=0.05,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    bias="none", task_type="CAUSAL_LM",
)

TrainingArguments(
    num_train_epochs=3,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,           # effective batch = 16
    learning_rate=2e-4,
    lr_scheduler_type="cosine",
    warmup_ratio=0.03,
    optim="paged_adamw_8bit",
    fp16=True,                               # T4 doesn't have bf16
    logging_steps=10, eval_steps=50, save_steps=100,
)
```

## Reproducibility

- Random seed: 42 (set in train.py and build_dataset.py)
- Training data: deterministic synthesis from seed_examples.jsonl
- Model: `google/gemma-4-2b-it` from HuggingFace (gated — accept license once)
- Tokenizer: same as base
- Hash of dataset committed in `data/dataset_hash.txt` for verification

## Limitations honestly stated

- The synthetic dataset (250 examples) is small. Real production training
  would want 5,000+ human-curated examples.
- We don't fine-tune the multimodal vision branch — only the text model.
  Chart-image analysis still uses the base model.
- The adapter improves SEBI-citation accuracy but doesn't add new factual
  knowledge beyond what's in the 5 seed docs.
- Ollama runtime support for LoRA adapters is via merge-and-quantize, not
  hot-swap. See `docs/finetune-results.md` for the merge pipeline.

## Attribution

Gemma is a trademark of Google LLC. Finsight OS is an independent project and
is not affiliated with or endorsed by Google.
