# Run ledger

`ledger.csv` holds one row per (run, star, period, metric): every
configuration we have scored and its result. FINDINGS.md explains the
results; the ledger is the table to search when choosing the best
combination.

Rules:
- Every scored run gets rows here in the same commit as its FINDINGS
  entry.
- Rows from different exposure sets are not comparable. Compare
  configurations only through paired rows (`baseline_run` set) on the
  same `exposure_set`.
- Effects measured separately do not necessarily add. A combination
  counts as tested only when it has its own run.
- Values come from result files or FINDINGS text, never from memory.
  `source` says which.

## Columns

| Column | Meaning |
|---|---|
| run_id | short unique id, e.g. `v5_x04_cti` |
| date | YYYY-MM-DD the run was scored |
| study | FINDINGS section / test-bed branch / specfast PR |
| commit | code commit that produced it, if known |
| extraction | `orig`, `x04`, `x04+trv02`, `neid-drp`, ... |
| chain | `legacy`, `charlie`, `v5`, `v5eq`, `joint`, ... |
| config | knobs that differ from the chain's default, `;`-separated |
| star | target name |
| period | `2016`, `2017-19`, `2018+`, `all`, ... |
| exposure_set | which exposures: `common3way`, `all`, `pre-realign-402`, ... |
| n_exp, n_nights | counts |
| metric | `ml_excess`, `wrms_nightly`, `rms_nightly`, `within_night`, `K`, `chi2r`, ... |
| value, ci_lo, ci_hi | result and 95% interval (blank if none) |
| baseline_run | run_id this row is paired against (blank if unpaired) |
| diff, diff_lo, diff_hi | paired difference vs baseline_run, 95% CI |
| source | `FINDINGS:<section date + title>` or a results-file name |
| notes | anything needed to read the row correctly |

## Measured separately, never combined

Each item below was scored only on its own (or only against a different
baseline). Measure the combination before assuming the gains add.

- **trv02 + original 2016 wavelength solution** (`v5_x04trv02` and
  `v5_x04ow16`): **pending**, running now; rows go in when FINDINGS
  reports it.
- trv02 + fibre-flat profile (`v5_x04trv02`, `v5_x04fprof16`).
- Any 2016 variant (trv02, fprof, ow) + per-frame trace re-measurement
  (not yet built).
- The 2016 variants + timing from 2018 only: every flat2016 run uses
  timing everywhere (`v5_x04`), not `v5_x04_timing18`.
- Timing from 2018 only + CTI (`v5_x04_timing18`, `v5_x04_cti`), and
  + the 100 e- count floor (`v5_x04_cti_floor100`).
- Timing from 2018 only + the exposure-meter record for 2016-17, the
  afexp recommendation (afexp scored the meter only on 2018-19).
- Static per-(tel, era) h3 (`charlie_orig_feedF2i`, L0 level) + the v5
  chain. Per-era B-star maps (Be0) were combined with v5 + CTI
  (`v5_x04_cti_be0`) and made tau Cet worse.
- NIST atlas + learned observer-frame correction
  (`charlie_orig_nist_obscorr`) + the v5 chain.
- Telluric mask 0.99 / 0.995 (L0 only) + NIST atlas or the v5 chain.
- The e2esim fixes (inferred template, per-era static table S, per-era
  LSF asymmetry): each simulated alone; no combined simulation or real
  run.
- The three cross-start conventions together (`v5eq_xs_all3`) were
  scored only as agreement with the test bed on 10 exposures, not as an
  RV-precision run; the 0.0625 km/s grid was scored alone
  (`v5eq_orig_g0625`).
- Inflating or gating x04's faint traces: proposed in overfit, not run.
