"""
Evaluate the COMPLETE pipeline (validator -> model -> mapper) on an independent test set.

    python scripts/evaluate.py --split-file models/waste_classifier/test_split.json
    python scripts/evaluate.py --data-dir my_own_photos/          # folders = class names

Reports (used in the project report / slides):
  * top-1 and top-3 accuracy                  (NFR-02, target >= 85 %)
  * category accuracy (recyclable/...)        (what the end user actually cares about)
  * share of "uncertain" predictions          (effect of the confidence threshold)
  * per-class precision/recall + confusion matrix
  * latency: mean, median, p95, max           (NFR-01, target p95 <= 2 s on CPU)
Everything is also written to evaluation_report.json (reproducibility, NFR-10).
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

# Allow running as "python scripts/evaluate.py" from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from waste_classification import ClassificationService, Settings, normalize_label  # noqa: E402

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def collect_samples(args) -> list:
    """List of {"path", "label"} from a split file or from an ImageFolder-style directory."""
    if args.split_file:
        return json.loads(Path(args.split_file).read_text(encoding="utf-8"))
    samples = []
    for class_dir in sorted(Path(args.data_dir).iterdir()):
        if class_dir.is_dir():
            samples += [{"path": str(f), "label": class_dir.name}
                        for f in sorted(class_dir.iterdir()) if f.suffix.lower() in IMAGE_SUFFIXES]
    return samples


def percentile(values, q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--split-file", help="test_split.json written by scripts/train.py")
    src.add_argument("--data-dir", help="folder with one sub-folder per class")
    ap.add_argument("--output", default="evaluation_report.json")
    args = ap.parse_args()

    settings = Settings.load()
    service = ClassificationService.from_settings(settings)
    samples = collect_samples(args)
    if not samples:
        sys.exit("No test images found.")
    print(f"Evaluating {len(samples)} images ...")

    y_true, y_pred, latencies = [], [], []
    top3_hits = category_hits = uncertain = errors = 0
    for s in samples:
        result = service.classify_file(s["path"])
        truth = normalize_label(s["label"])
        if result.is_error:
            errors += 1
            y_true.append(truth); y_pred.append("<error>")
            continue
        y_true.append(truth); y_pred.append(result.item)
        latencies.append(result.processing_ms)
        top3_hits += truth in [p.item for p in result.top_predictions]
        category_hits += result.category == service.mapper.to_category(truth)
        uncertain += result.status == "uncertain"

    n = len(samples)
    top1 = sum(t == p for t, p in zip(y_true, y_pred)) / n
    report = {
        "images": n,
        "errors": errors,
        "top1_accuracy": round(top1, 4),
        "top3_accuracy": round(top3_hits / n, 4),
        "category_accuracy": round(category_hits / n, 4),
        "uncertain_rate": round(uncertain / n, 4),
        "latency_ms": {
            "mean": round(statistics.mean(latencies), 1),
            "median": round(statistics.median(latencies), 1),
            "p95": round(percentile(latencies, 0.95), 1),
            "max": round(max(latencies), 1),
        } if latencies else {},
        "model_version": service.classifier.model_version,
        "confidence_threshold": settings.confidence_threshold,
    }

    # Per-class metrics + confusion matrix (scikit-learn is a dev dependency).
    try:
        from sklearn.metrics import classification_report, confusion_matrix
        labels = sorted(set(y_true))
        report["per_class"] = classification_report(
            y_true, y_pred, labels=labels, output_dict=True, zero_division=0)
        report["confusion_matrix"] = {"labels": labels,
                                      "matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist()}
        print(classification_report(y_true, y_pred, labels=labels, zero_division=0))
    except ImportError:
        print("(install scikit-learn for per-class metrics and the confusion matrix)")

    print(json.dumps({k: v for k, v in report.items() if k not in ("per_class", "confusion_matrix")}, indent=2))
    p95 = report["latency_ms"].get("p95", float("inf"))
    print(f"NFR-02 accuracy >= 85% : {'PASS' if top1 >= 0.85 else 'FAIL'}")
    print(f"NFR-01 p95 <= 2000 ms  : {'PASS' if p95 <= 2000 else 'FAIL'}")
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report written to {args.output}")


if __name__ == "__main__":
    main()
