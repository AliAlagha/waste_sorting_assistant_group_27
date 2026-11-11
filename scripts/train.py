"""
Fine-tune a pretrained image model on a waste dataset (transfer learning).

Run this on Kaggle / Google Colab with a free GPU, then download the output folder
into ``models/waste_classifier`` of this repository.

    python scripts/train.py --data-dir /kaggle/input/garbage-classification/garbage_classification

Dataset layout expected (torchvision ImageFolder): one sub-folder per class
    data_dir/battery/*.jpg, data_dir/biological/*.jpg, ...

What this script does
---------------------
1. Fixes all random seeds                               -> reproducible (NFR-10)
2. Splits the data into train / validation / TEST       -> independent test set (NFR-02)
3. Fine-tunes the model; keeps the epoch with the best VALIDATION accuracy
4. Evaluates ONCE on the untouched test set
5. Saves: model + processor, model_metadata.json (version, classes, metrics, seed),
          test_split.json (exact test files, reused by scripts/evaluate.py)

Credits: the training loop follows the common Hugging Face image-classification
fine-tuning recipe (ViT/Kaggle notebooks). Differences from the community notebook
we started from: seeded and reproducible, separate test split, best-checkpoint
selection, torch.optim.AdamW (transformers' AdamW was removed), metadata export.
"""
from __future__ import annotations

import argparse
import copy
import json
import random
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import torch
from torch.optim import AdamW
from torch.utils.data import DataLoader, random_split
from torchvision.datasets import ImageFolder
from tqdm.auto import tqdm
from transformers import AutoImageProcessor, AutoModelForImageClassification, get_scheduler


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data-dir", required=True, help="ImageFolder dataset root")
    p.add_argument("--output-dir", default="models/waste_classifier")
    # MobileNetV2 is small/fast on CPU (NFR-01). For higher accuracy try
    # "google/vit-base-patch16-224-in21k" (slower, ~340 MB).
    p.add_argument("--model-name", default="google/mobilenet_v2_1.0_224")
    p.add_argument("--epochs", type=int, default=10)
    p.add_argument("--lr", type=float, default=5e-5)
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--val-frac", type=float, default=0.15)
    p.add_argument("--test-frac", type=float, default=0.15)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--num-workers", type=int, default=2, help="use 0 on Windows")
    return p.parse_args()


def set_seed(seed: int) -> None:
    """Make runs repeatable."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


class Collator:
    """Turns a list of (PIL image, label) into model-ready tensors (resize + normalise)."""

    def __init__(self, processor) -> None:
        self.processor = processor

    def __call__(self, batch):
        inputs = self.processor([img for img, _ in batch], return_tensors="pt")
        inputs["labels"] = torch.tensor([label for _, label in batch], dtype=torch.long)
        return inputs


@torch.no_grad()
def accuracy(model, loader, device) -> float:
    """Top-1 accuracy of ``model`` on ``loader``."""
    model.eval()
    correct = total = 0
    for batch in loader:
        batch = {k: v.to(device) for k, v in batch.items()}
        preds = model(**{k: v for k, v in batch.items() if k != "labels"}).logits.argmax(-1)
        correct += (preds == batch["labels"]).sum().item()
        total += batch["labels"].numel()
    return correct / max(total, 1)


def main() -> None:
    args = parse_args()
    set_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    # ---- data ---------------------------------------------------------------
    dataset = ImageFolder(args.data_dir)
    classes = dataset.classes
    n = len(dataset)
    n_test, n_val = int(n * args.test_frac), int(n * args.val_frac)
    n_train = n - n_val - n_test
    train_ds, val_ds, test_ds = random_split(
        dataset, [n_train, n_val, n_test], generator=torch.Generator().manual_seed(args.seed))
    print(f"Classes ({len(classes)}): {classes}")
    print(f"Split -> train {n_train} | val {n_val} | test {n_test}")

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    # Remember exactly which files are in the test set (used by scripts/evaluate.py).
    test_files = [{"path": dataset.samples[i][0], "label": classes[dataset.samples[i][1]]}
                  for i in test_ds.indices]
    (out / "test_split.json").write_text(json.dumps(test_files, indent=2), encoding="utf-8")

    # ---- model --------------------------------------------------------------
    processor = AutoImageProcessor.from_pretrained(args.model_name)
    model = AutoModelForImageClassification.from_pretrained(
        args.model_name,
        num_labels=len(classes),
        id2label={i: c for i, c in enumerate(classes)},
        label2id={c: i for i, c in enumerate(classes)},
        ignore_mismatched_sizes=True,      # replace the original classification head
    ).to(device)

    collate = Collator(processor)
    train_loader = DataLoader(train_ds, args.batch_size, shuffle=True, collate_fn=collate,
                              num_workers=args.num_workers)
    val_loader = DataLoader(val_ds, args.batch_size, collate_fn=collate, num_workers=args.num_workers)
    test_loader = DataLoader(test_ds, args.batch_size, collate_fn=collate, num_workers=args.num_workers)

    optimizer = AdamW(model.parameters(), lr=args.lr)
    total_steps = args.epochs * len(train_loader)
    scheduler = get_scheduler("linear", optimizer, num_warmup_steps=0, num_training_steps=total_steps)

    # ---- training loop ------------------------------------------------------
    best_val, best_state = -1.0, None
    for epoch in range(1, args.epochs + 1):
        model.train()
        running = 0.0
        for batch in tqdm(train_loader, desc=f"Epoch {epoch}/{args.epochs}"):
            batch = {k: v.to(device) for k, v in batch.items()}
            loss = model(**batch).loss          # labels are in the batch -> loss is computed
            loss.backward()
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
            running += loss.item()
        val_acc = accuracy(model, val_loader, device)
        print(f"Epoch {epoch}: train loss {running / len(train_loader):.4f} | val acc {val_acc:.4f}")
        if val_acc > best_val:                  # keep the best epoch, not simply the last
            best_val, best_state = val_acc, copy.deepcopy(model.state_dict())

    model.load_state_dict(best_state)

    # ---- final, one-time test evaluation -----------------------------------
    test_acc = accuracy(model, test_loader, device)
    print(f"\nBest val acc: {best_val:.4f} | TEST acc: {test_acc:.4f}")

    # ---- save ---------------------------------------------------------------
    model.save_pretrained(out)
    processor.save_pretrained(out)
    metadata = {
        "model_version": f"{Path(args.model_name).name}-{date.today().isoformat()}",
        "base_model": args.model_name,
        "dataset": str(args.data_dir),
        "classes": classes,
        "seed": args.seed,
        "split": {"train": n_train, "val": n_val, "test": n_test},
        "hyperparameters": {"epochs": args.epochs, "lr": args.lr, "batch_size": args.batch_size},
        "val_accuracy": round(best_val, 4),
        "test_accuracy": round(test_acc, 4),
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    (out / "model_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Model saved to {out.resolve()}")


if __name__ == "__main__":
    main()
