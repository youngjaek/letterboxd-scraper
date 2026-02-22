# Distribution Buckets (Concept)

This document captures the quantitative rules we discussed for classifying cohort histograms into user-friendly buckets. Percentages refer to the share of cohort watchers whose ratings fall into a given band.

Notation:

- `P5`, `P4_5`, `P4`, ... `P0_5`: percentage of ratings at that exact star value.
- `HIEXTREME = P5 + P4_5`
- `HIGH = P5 + P4_5 + P4`
- `MIDHIGH = P3_5 + P3`
- `MIDLOW = P2_5 + P2`
- `LOW = P1_5 + P1 + P0_5`
- `LOWEXTREME = P1 + P0_5`
- `MID = MIDHIGH + MIDLOW`

## Masterpiece Consensus (current)

- `HIEXTREME >= 0.40`
- `LOW <= 0.10`
- `P5 >= 1.2 * max(P4_5, P4, P3_5, P3, P2_5, P2, P1_5, P1, P0_5)`

## Future Buckets (reference only)

The following thresholds are on hold; we may reintroduce them later:

- **Certified Favorite**: `HIGH + MIDHIGH >= 0.70`, `0.20 <= HIEXTREME <= 0.40`, `LOW <= 0.15`, `MIDHIGH >= MIDLOW`
- **Cult Darling**: `HIGH + MIDHIGH >= 0.60`, `LOW >= 0.10`, `HIEXTREME < 0.35`, `LOW >= 0.4 * HIEXTREME`
- **Steady Crowdpleaser**: `MID >= 0.75`, `abs(MIDHIGH - MIDLOW) <= 0.10`, `HIGH <= 0.15`, `LOW <= 0.15`
- **Even Split**: `MID >= 0.60`, `0.10 <= HIGH <= 0.20`, `0.10 <= LOW <= 0.20`, `abs(HIGH - LOW) <= 0.05`
- **Balanced Chaos**: each of `HIGH`, `MID`, `LOW` between `0.20` and `0.40`, and `max(bucket_i) - min(bucket_i) <= 0.15`
- **Consensus Bomb**: `LOWEXTREME >= 0.40`, `HIGH <= 0.10`, `LOWEXTREME >= 1.6 * max(MIDLOW, MIDHIGH, HIGH)`
- **General Dislike**: `LOW + MIDLOW >= 0.70`, `0.20 <= LOWEXTREME <= 0.40`, `HIGH <= 0.20`
- **Polarizing Trainwreck**: `LOWEXTREME >= 0.30`, `HIEXTREME >= 0.10`, `MID <= 0.40`, `min(LOWEXTREME, HIEXTREME) >= 0.25 * max(LOWEXTREME, HIEXTREME)`

## Reference Image

The mock alignment charts live at `logs/distribution-charts.jpeg` to keep them out of git history while still accessible locally.

## Inspecting Individual Films

To fetch the full metadata for a single film (watchers, histogram counts, and the assigned bucket) run:

```
python scripts/inspect_distribution.py --cohort 8 --slug pulse-2001 [--query "&decade=2000"]
```

The script reads `NEXT_PUBLIC_API_BASE_URL` and `NEXT_PUBLIC_API_KEY` from your environment (matching `.env.local`).
```
