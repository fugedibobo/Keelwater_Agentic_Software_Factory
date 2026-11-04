# Synthetic delivery data

**This data is invented.** Keelwater is a fictional company; no real company, person or system produced these rows. It exists so the board tracker in `scripts/halving_model.py` has something to read.

## How it was generated

`uv run python scripts/halving_model.py --generate` writes `items.csv` deterministically (`random.Random(42)`, no clock input), so two runs give identical bytes.

- 5 squads (the squad names in `config/taxonomy.yaml`), 6 months from 01/05/2026 (two quarters; month 1 = May 2026), 25-40 items per squad per month before the pilot adjustment, 990 rows in all.
- Each item is a piece of work released to customers in that month (the release time is drawn uniformly inside the month). Stage durations are worked backwards from it, so ideas can start before 01/05/2026.
- A stage lasts 180 days x its mid share in `config/halving_inputs.yaml` x a lognormal noise factor (mean 1, sigma 0.25). 180 days is the 6-month idea-to-adoption cycle assumption in the research note.
- **Pilot:** `intake_claims` improves from month 4. Its stage times are multiplied by the mid `ai_plus_process` effects (AI effect x mid adoption ramp, process effect x phase-in, with the pilot clock starting at month 4). Its item count is divided by the same average multiplier (Little's law: faster flow, more items released).
- **Other squads** barely move: stage times shrink by 0.3% per month.
- Simplification: the pilot gain is keyed to the release month, not the month the work started, so it appears with no lag. Real gains lag.

## Columns (`items.csv`)

ISO timestamps, no time zone. `item_id`, `squad`, then one timestamp per stage boundary:
`idea`, `decision` (end of discovery and decision), `spec` (specification signed off), `build_start`, `pr_opened`, `pr_merged` (end of review), `tested`, `flag_on` (code live behind a flag), `customer_released`, `adopted`.
Here `spec` equals `build_start`, and `tested` equals `flag_on` (no queue between them).

- idea_to_production_behind_flag = `flag_on` - `idea`
- idea_to_customer = `customer_released` - `idea`
- time to adoption = `adopted` - `customer_released` (not part of either lead-time target)

## Tracker windows

`uv run python scripts/halving_model.py --track data/delivery/items.csv`

- Baseline: items released in months 1-3 (May to July 2026). Lead time is the median across those items (all squads pooled for "overall"; a squad's own items for a squad row). Throughput is the mean items released per squad per month.
- Current: items released in the last two months in the file (months 5-6, September and October 2026).
- Lead-time progress = (baseline - current) / (baseline x 0.5): 100% means lead time has halved.
- Throughput progress = (current - baseline) / baseline: 100% means shipped work per squad per month has doubled.
- Displayed values are clamped to 0-100%; the raw number is printed beside it. Output also goes to `reports/halving/tracker.md`.
