# Receipt-scan accuracy benchmark

Scores how well BFF reads receipts, field by field, using the exact model call and
clean-up the app uses. Compare models and prompt versions before changing what ships.

## Try it

```bash
python -m benchmark.run --samples --models gpt-5.4-mini gpt-4o-mini
```

`samples/` holds three synthetic receipts (a subtotal that isn't the total, a US-style
date, a receipt with no total). Real receipts are much harder; use them for real numbers.

## Run it on real receipts

1. Put photos in `benchmark/receipts/` (gitignored, never committed). JPEG, PNG or WebP.
   iPhone photos are often HEIC; convert them on a Mac with
   `sips -s format jpeg benchmark/receipts/*.HEIC --out benchmark/receipts/`.
2. Create `benchmark/receipts/labels.csv` with the correct answer for each photo:

   ```csv
   file,merchant,amount,date,category,currency
   IMG_0412.jpg,Trader Joe's,23.40,2026-11-02,Groceries,USD
   IMG_0413.jpg,Chipotle,11.85,2026-11-03,Food & Dining,USD
   ```

   - `amount` = the final total paid (after tax and tip), not the subtotal.
   - `date` = YYYY-MM-DD. `category` = one of the app's categories.
   - Leave a cell blank if the receipt doesn't show it (for example no currency symbol);
     then only a blank answer counts as right.
3. Run `python -m benchmark.run` (add `--models` to compare models).

## Options

| Flag | What it does |
| --- | --- |
| `--models A B` | Run several models (default: the app's `OPENAI_MODEL`) |
| `--prompt-file path.txt` | Also run an alternative system prompt (repeatable) |
| `--price-in X --price-out Y` | Add a cost-per-scan column ($ per 1M input / output tokens) |
| `--images DIR` | Use another folder with images + `labels.csv` |

## Output

A summary table (printed, and saved to `benchmark/results/<time>-summary.md`) with
accuracy per field, **all 4 correct** (merchant, amount, date and category all right: the
PRD's scan success rate), median seconds and average tokens per scan. The per-receipt
detail CSV shows what was expected vs. returned for every field. `results/` is gitignored
because it contains what's on your receipts.

## Scoring rules

- Merchant: case and punctuation ignored; "TRADER JOE'S #552" matches "Trader Joe's".
- Amount: within $0.01.
- Date, category, currency: exact.
- A field the scan left blank is wrong, unless the receipt doesn't show it.
