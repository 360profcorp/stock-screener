# AI ranking v2.1 — result (PREREG v2.1)

Run `research/results/ai_rank/v2_train/2026-10-21T0006Z/` (workflow run 39519200849), on the
audited v2 dataset (sha256 `e1b40d2f…`, rank_rs fix applied). The gate was written to
`gate.json` at 2026-10-21 00:16 UTC, **before** the historical window was computed.

## Verdict: **FAILED — RS-first stays.** Nothing is frozen; no shadow stage.

## Deciding run (retest, PIT S&P 500, 26 features)
- **Chosen on validation** by mean daily rank correlation (IC): ridge, alpha 100, with IC
  +0.015 over 126 days. Every one of the 7 configurations had a validation IC below 0.016.
- **Walk-forward** (train before year Y, score year Y):

| Year | Train labels | IC (days) | Model return | RS-first return | Gap |
|---|---|---|---|---|---|
| 2023 | 203 | skipped (< 500 labels, §4) | | | |
| 2024 | 1,704 | +0.025 (185) | +19.8 % | +22.7 % | −2.9 pp |
| 2025 | 3,603 | **−0.045** (168) | +13.2 % | +23.9 % | **−10.7 pp** |

- **Pooled walk-forward IC:** −0.008, bootstrap 90 % interval [−0.048, +0.029] over 353 days.
- **Validation portfolio:** model +12.6 % against RS-first +31.1 % and a random-order median of
  +17.7 %.

| Gate (§4) | Result |
|---|---|
| G1: IC > 0 in every walk-forward year and on validation | **FAIL** (2025: −0.045) |
| G2: pooled IC ≥ 0.03 and its 90 % interval above 0 | **FAIL** (−0.008) |
| G3: no year worse than RS-first by more than 2 pp, and beats random on validation | **FAIL** (−10.7 pp; 12.6 % < 17.7 %) |

## Reported only (can never pass the gate)
- **Sensitivity (+ `earn_within_5`, the flagged look-ahead feature):** also fails. Walk-forward IC
  is +0.054 in 2024 and −0.047 in 2025, pooled +0.006. The portfolio is worse than RS-first by
  up to 14.4 pp.
- **All four long setups (`rank_rs_all` + setup dummies):** walk-forward IC is positive every
  year (+0.046 / +0.052 / +0.025), pooled **+0.041 with a 90 % interval of [+0.026, +0.056]**.
  So G1 and G2 would hold. The portfolio is mixed: 2023 −1.7 % against +8.4 % for RS-first,
  2024 +33.1 % against +25.3 %, 2025 +17.7 % against +6.5 %, so G3 fails. The likely source of
  the skill is choosing *between setups* (for example retest/VCP over breakout), not ordering
  retests. This is a **hypothesis for a new pre-registered study**, not a result.

## Historical window 2025-12-30 → 2026-10-14 (NOT independent, computed once after the gate)
- Model +14.0 % (DD −14.1 %) against RS-first +27.5 % (DD −7.7 %). The random-order median is
  +7.6 %.
- IC +0.054 over 135 days, 90 % interval [−0.005, +0.110], which includes 0. This window does not
  change the decision.

## Conclusion
Inside one setup, the new information (earnings timing, sector strength, breadth) does not
order retests better than RS. The validation IC is close to 0 and the sign flips between years.
RS-first remains the ranking of the paper portfolio.

## Possible next step (owner decision; would need a new pre-registration)
Study **setup selection** across retest, breakout and VCP on the same day, since that is where
the secondary run found a stable IC. Use its own protocol, with a forward shadow test only.
