# specfast: findings log

Dated conclusions from the experiments run on Charlie's code (the test
bed). Each entry: what was tested, the result, what it means for the
design, and where the code and data live. DESIGN.md holds the current
architecture; this file holds the evidence behind it. Newest last.

Paths: test-bed repo `/pool/radish1/minerva-rv/charlie` (branches named
below, local only); results `/pool/radish1/minerva-rv/work/results/`.

## 2026-11-20 Reproduction and review of Charlie's code

- Reproduced 51 Peg: K = 54.0 +/- 1.9 m/s (DSST), against Charlie's 52.6 +/- 3.6.
- Review: `/pool/radish1/minerva-rv/review/review.md`. Verdict: (c),
  inspiration only. JDE: keep the code as the test bed; specfast is the
  replacement.
- Per-exposure errors are formal weighted-mean errors (1/sqrt(sum w)),
  not order-to-order spread.
- The self-calibration subtracts per-(telescope, order) offsets of
  ~250 m/s rms. The 51 Peg K depends on the estimator: median 54.0,
  leave-one-out 60.8, two-way 55.0, none 59.1.
- Splitting each order into 4 velocity chunks improves the Wilson-window
  rms from 2.27 to 2.10 m/s. There is static structure between segments
  of one order. Design: per-segment velocities.

## 2026-11-20 B-star LSF (branch bstar-lsf)

- The B-star sigma map scatters 0.009 km/s (MAD), against 0.019 for
  daytime sky. 51 Peg K moves by at most 0.3 m/s.
- sigma varies along an order: ~9% broader in pixels toward the red.
- Design: B stars are the LSF calibration, and daytime sky is the last
  resort.

## 2026-11-20 Header and wavelength recovery (branches offsets-2018, standards)

- HD 122064 2018 zero-fits: a TARGRA -> TARGRAT header change (151 files).
  Fixing it recovers 25 RVs.
- Frames from Dec 2016 to Jan 2017 were reduced with a stale wavelength
  solution, off by ~70 px. `preshift.py` recovers 21 frames.
- Design: a header normalization layer; every failure is logged.

## 2026-11-20 Joint offset and error model (branch offsets-2018)

- Model: v = RV_e + O[group, era] + noise, sigma^2 = beta^2 sigma_i^2 + s^2,
  fitted by REML with the offsets marginalized.
- Errors are calibrated in the Wilson window (rms 2.44 m/s).
- 51 Peg K = 54.0-55.4 +/- 2.0-2.2 m/s, with an exposure random effect
  s_exp ~ 3 m/s.
- The |vsun| quality gate does not matter.

## 2026-11-20 Era breaks and global zero-points (branch standards)

- Era starts from the vacuum and thermometer logs: listed in DESIGN.md.
  Work in `/pool/radish1/minerva-rv/work/eras/`.
- Multi-star zero-points (y_s = gamma_s + Z[era]):
  - The realignment step is +9.4 +/- 1.0 m/s (delta chi^2 88).
  - 2019-09-18: +2.3 +/- 0.9 m/s, marginal.
  - The 2017 outage needs no zero-point of its own.
  - The 2016 step cannot be split between the September leak and the
    November opening.
- RMS before -> after the zero-points:

  | Star | Before | After |
  |---|---|---|
  | HD 122064 | 9.3 | 8.5 |
  | tau Cet | 4.9 | 4.6 |
  | sigma Dra | 11.4 | 9.7 |
  | HD 62613 | 10.9 | 10.0 |
  | HD 26965 | 6.4 | 6.0 |
  | 61 Cyg A | 6.8 | 6.7 |
  | iota Per | 6.4 | 6.6 |

- Open: iota Per shows no 2016 jump.

## 2026-11-20 Why not Keck precision (diagnosis)

- Within a night the scatter is at or below the formal errors (tau Cet
  1.5 vs 2.1 m/s), so S/N does not dominate.
- Night to night there is 4-13 m/s of scatter, already full at a 1-day lag.
- Nightly RVs from different telescopes correlate at only 0.04-0.12.
  Telescopes 1 and 2 (~13 m/s) are worse than 0 and 3 (5-8 m/s).
- The error does not correlate with the barycentric velocity or with
  |dBERV/dt|.
- Flux-weighted midpoint: FLUXMID equals the geometric midpoint in
  90-100% of frames before 2022. It is unused by the code, but not the
  dominant term.
- Leading suspect: the frozen LSF cannot track per-telescope, per-night
  changes in illumination. The free-LSF test (branch freelsf) is running.

## 2026-11-20 KiwiSpec optical model

- 7 constants per era fit iodine-anchored wavelength solutions to
  0.04-0.05 px. Details in DESIGN.md.
- The model is in the collaboration-private docs area
  (`/pool/radish1/minerva-rv/docs/kiwispec/`), which must not leave the
  collaboration.

## 2026-11-20 Wavelength ladder and stitching search (branch wavemodel)

- Data: 209 matched HD 122064 exposures from 2016-2020, plus 51 Peg.

  | Model | 2016-20 RMS (m/s) | sqrt(chi2_r) |
  |---|---|---|
  | Free quadratic | 10.1 | 1.68 |
  | Optical model + per-order offset and slope | 9.7 | 1.60 |
  | Free quartic | 9.4 | 1.51 |
  | Rigid optical model (x0 per fibre only) | 12.8 | 3.05 |

  The rigid model underestimates its errors by ~30%.
- The per-trace table is stable to ~0.015 px only, so keep per-order
  freedom.
- The optical model as the starting guess rescues 23 exposures from Dec
  2016 to Mar 2017.
- The ~250 m/s per-(telescope, order) offsets do not change with the
  wavelength model, so they are template or line-list zero points.
- No detector stitching: any step at a 512-px boundary is below ~0.02 px.
- There is a smooth optical along-order distortion of +/-0.1 px
  (~70-100 m/s), period ~800 px.
  - It is identical across orders and fibres within an era.
  - It follows the spectrum, not the detector, across the remount.
  - Design: a per-era calibration term D(x).
- Results: `work/results/wavemodel/`. Plot:
  `work/plots/wavemodel/stitch_overlay_W3.png`.
- Next: fix D(x) in the fit and re-run the quadratic and quartic, and the
  per-segment structure.

## Open threads

- Free-LSF ladder (L0 frozen to L3 sum of Gaussians) on tau Cet, sigma Dra
  and HD 122064: running.
- Flux-weighted midpoint: look for exposure-meter logs.
- iota Per's missing 2016 jump.
- Recalibrate the optical model from B-star frames.
- Inferred-template mode; Korg prototype; specfast skeleton.
