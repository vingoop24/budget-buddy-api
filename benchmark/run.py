"""Receipt-scan accuracy benchmark.

    python -m benchmark.run                               # your receipts, app's model + prompt
    python -m benchmark.run --samples                     # the two built-in synthetic receipts
    python -m benchmark.run --models gpt-5.4-mini gpt-4o-mini
    python -m benchmark.run --prompt-file benchmark/prompts/v2.txt
    python -m benchmark.run --price-in 0.15 --price-out 0.60   # $ per 1M tokens, adds cost

Runs the same model call and clean-up as the app on every labeled receipt, for every
model x prompt combination, and scores each field. Writes a per-receipt CSV and a
summary to benchmark/results/ (gitignored) and prints the summary.
"""

import argparse
import csv
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.services import ai, receipts
from benchmark.scoring import FIELDS, score

HERE = Path(__file__).parent
MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def load_labels(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        rows = [r for r in csv.DictReader(f) if r.get("file")]
    if not rows:
        sys.exit(f"No labeled receipts in {path}")
    return rows


def run_one(image: Path, model: str, prompt: str | None) -> tuple[dict, dict, float, str | None]:
    started = time.perf_counter()
    try:
        raw, tokens = ai.call_receipt_model(image.read_bytes(), MIME[image.suffix.lower()], model, prompt)
        return receipts.normalise(raw), tokens, time.perf_counter() - started, None
    except ai.AIUnavailable as exc:
        return {}, {}, time.perf_counter() - started, str(exc)[:200]


def pct(values: list[bool]) -> str:
    return f"{100 * sum(values) / len(values):.0f}%" if values else "–"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--samples", action="store_true", help="use benchmark/samples instead of benchmark/receipts")
    parser.add_argument("--images", type=Path, help="folder with receipt images and labels.csv")
    parser.add_argument("--models", nargs="+", default=[settings.openai_model])
    parser.add_argument("--prompt-file", type=Path, action="append", default=[],
                        help="alternative system prompt (repeatable); the app's prompt always runs too")
    parser.add_argument("--price-in", type=float, help="$ per 1M input tokens (for a cost column)")
    parser.add_argument("--price-out", type=float, help="$ per 1M output tokens")
    args = parser.parse_args()

    if not ai.ai_enabled():
        sys.exit("OPENAI_API_KEY is not set (put it in .env)")
    folder = args.images or (HERE / "samples" if args.samples else HERE / "receipts")
    labels = load_labels(folder / "labels.csv")
    prompts = [("app", None)] + [(p.stem, p.read_text()) for p in args.prompt_file]

    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    rows, summary = [], []

    for model in args.models:
        for prompt_name, prompt in prompts:
            scores, latencies, tin, tout, errors = [], [], [], [], 0
            for label in labels:
                image = folder / label["file"]
                if image.suffix.lower() not in MIME:
                    sys.exit(f"{image.name}: use JPEG, PNG or WebP (convert HEIC first, see benchmark/README.md)")
                predicted, tokens, seconds, error = run_one(image, model, prompt)
                s = score(predicted, label)
                scores.append(s)
                latencies.append(seconds)
                errors += error is not None
                if tokens.get("input_tokens") is not None:
                    tin.append(tokens["input_tokens"])
                    tout.append(tokens["output_tokens"] or 0)
                rows.append({
                    "model": model, "prompt": prompt_name, "file": label["file"],
                    **{f"expected_{f}": label.get(f, "") for f in FIELDS},
                    **{f"got_{f}": predicted.get(f, "") for f in FIELDS},
                    **{f"ok_{f}": s[f] for f in FIELDS},
                    "all_correct": s["all_correct"], "seconds": round(seconds, 2),
                    "input_tokens": tokens.get("input_tokens"), "output_tokens": tokens.get("output_tokens"),
                    "error": error or "",
                })
                mark = "ok " if s["all_correct"] else "MISS"
                print(f"  {mark} {model:<16} {prompt_name:<10} {label['file']}", file=sys.stderr)

            line = {
                "model": model, "prompt": prompt_name, "receipts": len(labels),
                **{f: pct([s[f] for s in scores]) for f in FIELDS},
                "all 4 correct": pct([s["all_correct"] for s in scores]),
                "median s": f"{statistics.median(latencies):.1f}",
                "avg tokens in/out": f"{statistics.mean(tin):.0f}/{statistics.mean(tout):.0f}" if tin else "–",
                "errors": errors,
            }
            if args.price_in is not None and args.price_out is not None and tin:
                per = (statistics.mean(tin) * args.price_in + statistics.mean(tout) * args.price_out) / 1e6
                line["$ per scan"] = f"{per:.5f}"
            summary.append(line)

    detail = out_dir / f"{stamp}-detail.csv"
    with detail.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    headers = list(summary[0])
    table = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    table += ["| " + " | ".join(str(r.get(h, "")) for h in headers) + " |" for r in summary]
    text = (f"Receipt-scan benchmark {stamp} · {len(labels)} receipts from {folder.name}/\n\n"
            + "\n".join(table) + "\n\n'all 4 correct' = merchant, amount, date and category all right "
            "(the PRD's scan success rate). A blank answer is right only when the receipt "
            "doesn't show that field (blank in labels.csv).\n")
    (out_dir / f"{stamp}-summary.md").write_text(text)
    print(text)
    print(f"Per-receipt detail: {detail}")


if __name__ == "__main__":
    main()
