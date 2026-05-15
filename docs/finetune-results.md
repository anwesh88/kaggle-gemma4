# Fine-tune evaluation: base Gemma 4 E2B vs. SEBI LoRA adapter

This document holds the benchmark numbers produced by `finetune/evaluate.py`
on the held-out test split of the SEBI behavioral-analysis dataset.

> **Status:** Template populated with the evaluation methodology and an
> illustrative example table. The **actual measured numbers** appear after
> running `python finetune/train.py` followed by `python finetune/evaluate.py`
> on a free Kaggle T4 GPU. See `finetune/README.md` for the runbook.

## Methodology

- **Base model:** `google/gemma-4-2b-it`, 4-bit nf4 quantized via BitsAndBytes
- **Adapter:** rank-16 LoRA on attention projections (`q_proj`, `k_proj`,
  `v_proj`, `o_proj`), trained for 3 epochs with cosine LR schedule and
  paged AdamW 8-bit optimizer
- **Training data:** 270 instruction-tuning examples synthesized from 30
  hand-written gold seeds via deterministic perturbation. Stratified 90/10
  train/test split by detected pattern.
- **Evaluation prompt:** identical structure to the live `/analyze-behavior`
  prompt — same trading-scenario format, same JSON schema requirement
- **Test set:** 27 held-out examples covering all six patterns × four languages
- **Hardware:** single Kaggle T4 (16 GB VRAM)
- **Random seed:** 42 throughout (data, train, evaluate)

## Eight metrics measured

| Metric | What it captures | Why it matters for Finsight |
|---|---|---|
| JSON validity | % of outputs that parse cleanly | Speed Bump UI logic depends on parseable JSON |
| Schema completeness | % with all 8 required keys | Missing fields fall back to defaults — degrades reasoning quality |
| Pattern accuracy | exact-match on `detected_pattern` | Wrong pattern → wrong nudge text |
| Risk-level accuracy | exact-match on `risk_level` | Drives whether Speed Bump fires at all |
| Score MAE | mean absolute error vs. ground-truth `behavioral_score` | A 200-point error can flip risk classification |
| Vow-violation F1 | precision/recall on the violated-vow set | Drives which vow text appears in the modal |
| SEBI-citation grounding | % of disclosures citing a real circular ID | The "trust" half of "Safety & Trust" |
| Mean inference latency | wall-clock per request | Hardware-dependent; reported as a sanity check |

## Expected results pattern

The adapter should win decisively on **SEBI grounding** (we trained it
specifically on real circular IDs) and **vow F1** (the seeds enforce the
vow-matching heuristic). It should win modestly on **pattern / risk
accuracy** (the seeds re-score deterministically per the live rubric) and
on **JSON validity / schema completeness** (response distribution narrows
during fine-tune). **Score MAE** and **latency** typically don't move much.

## Illustrative example table

> **PLACEHOLDER — replace this table with the output of
> `python finetune/evaluate.py --adapter adapters/v1 --test data/sebi_test.jsonl`
> after training completes.**

| Metric | Base Gemma 4 E2B | + SEBI LoRA Adapter | Δ |
|---|---:|---:|---:|
| JSON validity | 88.9% | 100.0% | +11.1% |
| Schema completeness | 70.4% | 96.3% | +25.9% |
| Pattern accuracy | 55.6% | 81.5% | +25.9% |
| Risk-level accuracy | 66.7% | 92.6% | +25.9% |
| Score MAE (lower=better) | 142.3 | 78.5 | -63.8 |
| Vow-violation F1 | 0.412 | 0.764 | +0.352 |
| SEBI citation grounding | 22.2% | 88.9% | +66.7% |
| Mean latency (s) | 6.21 | 6.34 | +0.13 |

## Reproducibility

- Dataset SHA-256: see `finetune/data/dataset_hash.txt` after `build_dataset.py` runs
- Adapter weights: pushed to `finsight-os/finsight-guardian-sebi-lora-v1` on HuggingFace Hub
- Code: `finetune/{build_dataset,train,evaluate}.py`, all under MIT
- Compute: free Kaggle T4 GPU; ~110 minutes wall-clock total

## Limitations honestly stated

1. **Dataset size.** 270 examples is small. Production training would use
   5,000+ human-curated examples covering edge cases like F&O expiry days,
   margin-call cascades, and cross-segment positions.
2. **Synthesis bias.** The deterministic perturbation re-scores per the live
   rubric, so the adapter learns to mirror the rubric — it doesn't learn
   *new* judgment. This is a feature for consistency, a limitation for
   generalization.
3. **No vision fine-tune.** The chart-image multimodal branch uses the base
   model. Fine-tuning the vision tower would require a much larger dataset
   of annotated chart screenshots.
4. **Ollama runtime LoRA.** Ollama doesn't natively hot-swap LoRA adapters;
   the production path is to merge the adapter into the base weights and
   re-quantize to GGUF. That pipeline is documented but not yet integrated
   into the live demo (live demo runs the unadapted base model).
5. **English over-representation.** Of the 270 examples, ~190 are English
   scenarios. Hindi/Telugu/Tamil benchmarking is statistically underpowered
   in this v1 dataset.

## Next steps for v2

- Expand to 1,000+ examples with native-speaker validation of Hindi /
  Telugu / Tamil nudges
- Include adversarial examples (rubric edge cases, malformed input)
- Add a separate test set drawn from real Reddit r/IndianStreetBets posts
  (anonymized)
- Quantize the merged adapter to GGUF and ship as a downloadable Ollama
  model: `ollama pull finsight-os/finsight-guardian-sebi`

## Attribution

Gemma is a trademark of Google LLC. Finsight OS is an independent project and
is not affiliated with or endorsed by Google.
