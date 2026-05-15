"""
train.py — QLoRA fine-tune Gemma 4 E2B on the SEBI behavioral-analysis dataset.

Hardware
--------
Designed for a single T4 GPU (16 GB VRAM, free on Kaggle and Colab).
Trains in ~90-120 minutes. On A100 it's 15-25 minutes.

Approach
--------
4-bit nf4 quantization of the base model (BitsAndBytesConfig) keeps base
weights at ~2 GB VRAM. Rank-16 LoRA adapters on attention projections add
~12 M trainable parameters (~50 MB on disk). Effective batch 16 via
gradient accumulation. Cosine LR schedule, paged AdamW 8-bit optimizer.

Usage
-----
    python train.py \
        --dataset data/sebi_train.jsonl \
        --base-model google/gemma-4-2b-it \
        --output adapters/v1 \
        --epochs 3

Push to HuggingFace Hub once trained:
    huggingface-cli login
    python -c "from peft import PeftModel; \
               PeftModel.from_pretrained(...).push_to_hub('finsight-os/finsight-guardian-sebi-lora-v1')"
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import torch
from datasets import load_dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM, AutoTokenizer,
    BitsAndBytesConfig, TrainingArguments,
)
from trl import SFTTrainer

SEED = 42


def build_bnb_config() -> BitsAndBytesConfig:
    """4-bit nf4 quantization — the cheapest QLoRA setup."""
    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )


def build_lora_config() -> LoraConfig:
    """Rank-16 adapters on the four attention projections."""
    return LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True,
                        help="Path to the JSONL training file (output of build_dataset.py)")
    parser.add_argument("--base-model", default="google/gemma-4-2b-it",
                        help="HuggingFace model id of the base. Note: Gemma is gated; "
                             "you must accept the license once at huggingface.co.")
    parser.add_argument("--output", default="adapters/v1",
                        help="Directory where the trained adapter will be written")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--per-device-batch-size", type=int, default=4)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--max-seq-length", type=int, default=1024)
    args = parser.parse_args()

    torch.manual_seed(SEED)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Load tokenizer + base model ──────────────────────────────────────
    print(f"[train] Loading base model {args.base_model} in 4-bit…")
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        quantization_config=build_bnb_config(),
        device_map="auto",
        torch_dtype=torch.float16,
        attn_implementation="eager",   # safer on T4 than flash-attn
    )
    model.config.use_cache = False
    model.config.pretraining_tp = 1

    # ── Wrap in LoRA ─────────────────────────────────────────────────────
    print("[train] Preparing for QLoRA…")
    model = prepare_model_for_kbit_training(model)
    model = get_peft_model(model, build_lora_config())
    model.print_trainable_parameters()

    # ── Load dataset ─────────────────────────────────────────────────────
    print(f"[train] Loading dataset {args.dataset}")
    ds = load_dataset("json", data_files=args.dataset, split="train")
    print(f"[train] {len(ds)} training examples")

    # ── Trainer ──────────────────────────────────────────────────────────
    training_args = TrainingArguments(
        output_dir=str(out_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.per_device_batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.learning_rate,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        optim="paged_adamw_8bit",
        fp16=True,
        bf16=False,
        logging_steps=10,
        save_steps=100,
        save_total_limit=2,
        report_to=[],                    # no wandb / tensorboard noise
        seed=SEED,
        gradient_checkpointing=True,
    )

    trainer = SFTTrainer(
        model=model,
        train_dataset=ds,
        dataset_text_field="text",
        tokenizer=tokenizer,
        args=training_args,
        max_seq_length=args.max_seq_length,
        packing=False,
    )

    print(f"[train] Starting training for {args.epochs} epochs…")
    trainer.train()

    # ── Save adapter ─────────────────────────────────────────────────────
    print(f"[train] Saving adapter to {out_dir}")
    trainer.model.save_pretrained(str(out_dir))
    tokenizer.save_pretrained(str(out_dir))

    # Light sanity check: load+infer one example
    print("[train] Quick sanity check on adapter…")
    sample_prompt = (
        "<start_of_turn>user\n"
        "You are Finsight OS. Analyze: 4 losses, ₹-9000 P&L, 85% margin. "
        "Reply with JSON only.\n<end_of_turn>\n<start_of_turn>model\n"
    )
    inputs = tokenizer(sample_prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=200, do_sample=False)
    print("[train] Sample output:")
    print(tokenizer.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True))

    print(f"\n[train] Done. Adapter at {out_dir}")
    print(f"[train] Push to Hub:  huggingface-cli login && \\")
    print(f"            python -c \"from peft import PeftModel; "
          f"PeftModel.from_pretrained(...).push_to_hub('finsight-os/finsight-guardian-sebi-lora-v1')\"")


if __name__ == "__main__":
    main()
