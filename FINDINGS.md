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

- Within a night the scatter is close to the formal errors, so S/N does
  not dominate the long-term rms. My first number (tau Cet 1.5 vs 2.1 m/s)
  used a different definition. The free-LSF run measures 2.89 m/s rms
  about each night's weighted mean, on nights with >= 2 exposures; its
  median error is 2.11.
- Night to night there is 4-13 m/s of scatter, already full at a 1-day lag.
- Nightly RVs from different telescopes correlate at only 0.04-0.12.
  Telescopes 1 and 2 (~13 m/s) are worse than 0 and 3 (5-8 m/s).
- The error does not correlate with the barycentric velocity or with
  |dBERV/dt|.
- Flux-weighted midpoint: FLUXMID equals the geometric midpoint in
  90-100% of frames before 2022. It is unused by the code, but not the
  dominant term.
- First suspect: the frozen LSF cannot track per-telescope, per-night
  illumination changes. The free-LSF test (below) largely rules this out.

## 2026-11-20 KiwiSpec optical model

- 7 constants per era fit iodine-anchored wavelength solutions to
  0.04-0.05 px. Details in DESIGN.md.
- The model and its write-up are collaboration-private and stay out of
  this repo.

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
  **Corrected 2026-11-22:** they are mostly the I2_0.1 atlas's
  air-dispersion error; see "Iodine atlas and learned observer-frame
  correction".
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

## 2026-11-21 Free-LSF ladder (branch freelsf)

Tested on tau Cet (331 exposures), sigma Dra (395) and HD 122064. Levels:

- L0: frozen B-star sigma (production; reproduced bit-identical).
- L1: free sigma per (exposure, tel, order).
- L2: L1 plus Gauss-Hermite h3.
- L3: sum of Gaussians.
- S0-S3: shared variants.
  - S0: a fixed sigma and h3 per (tel, order, era).
  - S1: one sigma scale per (exposure, tel).
  - S2: S1 plus an h3 offset per (exposure, tel), on top of the fixed h3.
  - S3: the nightly h3 change only.

Results:

- No variant changes the nightly rms by more than about 3% on tau Cet
  (L0 4.62 m/s) or sigma Dra (11.17). L2 and L3 are worse.
- HD 122064: S3 improves the nightly rms 9.2 -> 8.1, but the within-night
  rms rises.
- sigma varies night to night by 1-3% per telescope, most on tel 1. It
  barely moves the velocity (10-25 m/s per unit scale, under 1 m/s in
  practice).
- h3 correlates with the per-telescope residual (pooled r +0.23 to +0.51;
  strongest on tels 1 and 2), and the sign is right. Correcting for it
  trims telescope-specific scatter by 5-15% but adds 5-8% within-night
  noise.
- Nightly means from different telescopes stay uncorrelated (r 0-0.2) at
  every level. So the nightly scatter is independent errors per
  telescope, averaged together. Look at the per-fibre light path and
  illumination, not a common LSF.
- Headers have no guiding-error, FWHM or seeing keywords. h3 correlates
  weakly with throughput (r +0.2 to +0.3) and with fibre position on the
  guider (YFIBER, up to +0.31).
- Lead: a fixed per-(tel, order) h3 pattern shrinks the era zero-point
  steps (two-star fit 10.9 / 13.5 -> 4.7 / 3.4 m/s). The steps are partly
  degenerate with a fixed LSF asymmetry; verify with the 7-star fit.
- Bug: `joint_offsets.joint_fit` references errors to the mean of all
  exposures, including ones dropped later, which inflates rv_err
  (tau Cet L1 median 2.56 -> 3.57). Fixed in `freelsf_eval`; still
  present in `standards_eval.level1`.

Decision: keep the frozen symmetric sigma. If an LSF term is ever added,
use a shared h3 per (exposure, tel), regularized (nightly average, or a
model in throughput and fibre position).

Results: `work/results/freelsf/`; plots in `work/plots/freelsf/`.

## 2026-11-21 Fibre cross-talk / extraction (branch xtalk)

- Slit order per spectral order is T1, T2, T3, T4: tels 1 and 2 (the worst)
  are the middle fibres, 15.5 px from each neighbour. The edge fibres sit
  next to the adjacent order's T4/T1 trace. That inter-order gap shrinks
  from ~44 px at one detector edge to ~10 px (~8 sigma) at the other
  (y < 400); below y ~ 400 it is the smallest separation on the chip
  (JDE pointed this out). Even there, the leakage after a local
  background is <= 3e-4.
- The cross-dispersion profile is Gaussian with sigma 1.3 px, so the
  neighbours are ~12 sigma apart. Leakage into a neighbour's aperture is
  a smooth scattered-light pedestal (0.5-1.4% in a box), not a profile wing.
- Effective leakage in the delivered 1D spectra: 1e-5 to 7e-5 (pipeline
  v1.0.0, a simultaneous profile fit); <= 1e-3 in v0.x.
- Simulated sensitivity: same-order contamination ~0.03 m/s per 1%,
  because the ghost carries the iodine too. Cross-order ~0.5 m/s per 1%,
  and only on the edge fibres. Predicted error <= 0.15 m/s, against an
  observed 4-13 m/s.
- On real data, the neighbour-flux coefficient is consistent with zero
  for every star and telescope. Some own-throughput coefficients are
  significant: tau Cet tel 1 +10.4 +/- 2.8 m/s per dex; sigma Dra tel 0
  +10.6 +/- 3.0 and tel 1 +4.4 +/- 1.3. This points to the fibre's own
  illumination.
- Conclusion: cross-talk is ruled out. Extraction needs no rework for
  this; specfast's extraction requirements go in DESIGN.md.
- Legacy pipeline: v0.x fits each trace alone and zeroes windows below
  20 counts; v1.0.0 fits all 116 profiles per column jointly, plus a
  polynomial background. Raw 2D frames are in the observatory archive.
- Results: `work/xtalk/`. Raw frames: `data/raw2d/`.

## 2026-11-21 Guiding and flux-weighted midpoints (branch fluxmid)

Data found in the observatory archive:
- FAU guide images, 2015-2026. 2,324 of
  the 2,451 (exposure, telescope) pairs are usable.
- Guide-loop logs (minerva-control): star and fibre
  position per guide frame.
- Exposure-meter logs: 1 Hz, summed over
  all four fibres, 2016-2020 only.
- FLUXMID: minerva-control writes UNKNOWN. The old IDL values are
  unreliable (r = 0.04 against the FAU). The code uses DATE-OBS +
  EXPTIME/2.

Midpoint error:
- dt (flux-weighted minus geometric): robust sigma 2-5 s, rms ~40 s,
  dominated by rare lost-star cases. The per-telescope part is 24 s rms,
  uncorrelated between telescopes.
- Predicted barycentric error 0.2-0.7 m/s rms (2-2.5 with a coupling
  model), uncorrelated with the residuals. Midpoint corrections leave the
  per-telescope rms unchanged.
- Rejected as the cause.

The one real timing effect:
- In 2016-2020, 30-50% of (exposure, telescope) pairs have a guide gap of
  ~215 s (median) right after shutter open, and the star is 1.7" (median)
  off the fibre by the next frame.
- Suspected cause: `takeSpectrum` -> `getHdr` stalling the guide loop
  (control.py ~L1873); not proven.
- Correcting the epoch improves tau Cet nightly 4.63 -> 4.0-4.3 m/s (beats
  shuffled nulls); no effect on sigma Dra or HD 122064.
- To do: the robofast guider must keep imaging while headers are collected.

The per-telescope scatter is episodic:
- 2-13% of exposures beyond 4 MAD drive it; the core per-telescope sigma
  is only 2-3.3 m/s.
- T2, May-Jul 2019: the guider held the star 7-11" off the fibre.
- T2 on tau Cet, Oct-Nov 2018: about 1" off per the stamps, though the
  log says 0.3". Residuals -6 to -11 m/s, throughput -0.6 dex.
- In typical exposures T1 and T2 are not worse guided (median offset
  0.40", against 0.46-0.48" for T3 and T4).

Throughput dependence:
- Own relative throughput still predicts the residual: tau Cet T2
  +6.3 +/- 0.6 m/s per dex; T1 +3.6. Guiding offset and jitter do not
  explain it.
- For T2 the residual depends equally on relative and absolute flux, a
  count-level (S/N) bias on that trace. Candidate: charge-transfer
  inefficiency or nonlinearity (untested).

Time conventions: DATE-OBS is shutter-open UTC (2.3-2.4 s after the
control log). There is no constant clock offset (+17 +/- 29 s). The
barycentric and template-shift signs are correct.

Paths: `data/fau_stamps/`, `data/fau_logs/`, `data/expmeter/`,
`work/fluxmid/`, `work/results/fluxmid/`, `work/plots/fluxmid/`.

## 2026-11-21 Pre-2018 extractions were never redone

- In our copies and in the archived pipeline products, 2016 to
  mid-2018 is still v0.1-v0.6: per-trace +/-5 px window fits that zero
  low-flux windows. Five versions in two years.
- v1.0.0 (joint fit of all traces in a column, plus background) was
  only ever run forward from mid-2018.
- Raw 2D frames for every night are in the archive. A re-extraction
  test is proposed.

## 2026-11-21 Literature: MAROON-X (what it says about our suspects)

No published RV error budget table: checked Seifahrt+2018 (arXiv:1805.09276),
+2020 commissioning (2106.02157) and +2022 two-year review (2210.06563).

- Blending: the design requires >= 10 px between slices and orders.
  No measured cross-talk is published. Ji+2025 (arXiv:2505.19994) simulate
  it with an ESPRESSO-like PSF and box extraction (worst case): science-to-
  science contamination of 0.1% gives per-trace offsets up to a few m/s,
  reduced by averaging traces; below 0.01% it is negligible.
- Line-profile changes are their main long-term limit. After a 2021
  outage the profile width and shape changed, and these "have different
  impact on the calibration source and on stellar data and lead to
  unrecoverable RV offsets". An iodine cell avoids that mismatch only if
  the forward model captures the profile shape.
- Guiding: active tip-tilt at 1-10 s, requirement < 0.05 arcsec. The
  fibre and target positions are logged at the guide rate.
- Barycentric: they use an exposure meter, and plan a chromatic one for
  extinction-driven midpoint differences between arms.
- S/N changes between exposures: "no significant impact".
- Their precision: ~30 cm/s within a ~2-week run. Long-term run offsets
  are uncertain by 0.5-1.5 m/s (etalon chromatic drift). The instrument
  drifts 1.8-7 m/s per mK and ~10 m/s per night, removed by the
  simultaneous etalon.

## Open threads

- **Theoretical iodine atlas: shelved (JDE 2026-11-24).** Idea: replace or
  check the NIST FTS scan with a synthetic atlas from theoretical I2 B-X
  line positions (MHz-level) and strengths, forward-modelled through the
  LSF (observed iodine features at R ~ 80k are blends of many transitions
  with hyperfine structure, so centroids can't be mapped to line positions
  directly). Why shelved: the NIST scan's wavelength scale only shifts the
  zero point; its noise (0.3%/sample, ~0.18 m/s) and per-feature depth
  errors (1%, ~0.25 m/s) are far below the 1.75 m/s common excess. The one
  open atlas question is an ~8% static line-shape disagreement between the
  NIST scan and I2_0.1 at R = 80k. Revisit if the B-star local-window
  wavelength residuals show structure that follows iodine features rather
  than the detector or the optics. Public sources: no machine-readable B-X
  line list for 500-630 nm was found; options are a PGOPHER synthetic
  atlas from published constants, the Knoeckel, Bodermann & Tiemann (2004,
  EPJ D) line-position model (< 30 MHz, 2 sigma; distributed as IodineSpec,
  likely commercial), or the Ross & Salami (2005) Doppler-limited FTS atlas
  (14500-20000 cm-1, available from the authors on request).

- **B-star coverage caveat (2026-11-24).** Every B-star result so far
  (frozen LSF sigma per (telescope, order), the iodine and lsfgrad
  branches, the lsfillum static map) used 107 frames from 2017-03 to
  2018-02: a partial copy, not a data limit. The archive's pipeline
  products hold ~1,870 B-star frames over 2016-2026 in the same
  extraction as the star frames (2016: 831; 2019: 314; 2023-26 thin: 44,
  27, 25, 5). Per-era LSF maps are now built from 1,136 of them (lsfillum,
  2026-11-25); other conclusions that rest on one B-star year should be
  rechecked.

- Per-telescope nightly scatter (tels 1 and 2 worst): fibre illumination,
  guiding, modal noise, scrambling. Check FAU guide logs and fibre position.
- LSF asymmetry vs era steps: 7-star Z with a fixed h3 pattern.
- Fix the joint_fit error reference in standards_eval.
- The 96.5% K-recovery scale loss in injection tests (iodine branch).
- Continuum model: smooth 10-20 A residual structure the quadratic misses.
- The residual 41-59 m/s per-order offset pattern (DSST wavelength tilt?).
- T2 count-level slope (not the extraction, not detector nonlinearity):
  concentrated in Jul-Dec 2018, before the 2018-12-22 T2 throughput jump.
  Look at what changed in 2018-07 and 2018-12 (fibre, guiding, alignment).
  JDE (2026-11-22): December 2018 was a site trip. The mirrors were
  cleaned, and the main job was repairing T3, which had sheared its hard
  stop and wrapped its cables. On 2018-12-22: T2 throughput jumps, T2 LSF
  width +2.9% (gradient unchanged; corrected 2026-11-22 from "T1", a 0-based
  index slip), spectrograph temperatures flat
  (+/-0.01 C), iodine cell, CCD and pressure unchanged. So it is a
  telescope/fibre-side break. The cleaning included re-collimation, and
  the SBIG guide cameras were replaced with ZWOs on the same trip, so the
  guiding changed too (camera, pixel scale, cadence; header XFIBER/YFIBER
  are in different pixel units before and after). T3's fibre runs with its cables, so T3 data
  before the repair may carry fibre-stress (FRD / modal) effects.
- Flux-weighted midpoint: look for exposure-meter logs.
- iota Per's missing 2016 jump.
- Recalibrate the optical model from B-star frames.
- Inferred-template mode; Korg prototype; specfast skeleton.

## 2026-11-21: The two iodine atlases differ by air dispersion

Both atlases ship with the legacy pipeline (`minerva_dopcode/templates/`):

- `MINERVA_I2_0.1_nm.npy`:
  - 500-620 nm, resampled to a uniform grid in wavelength;
  - used by the legacy dopcode and by Charlie's code, where it is assumed
    to be in vacuum.
- `MINERVA_NIST_scan_201808.npy`:
  - 469-704 nm, still on its native FTS grid, uniform in wavenumber to
    1.7e-10, so its wavelength is exact vacuum 1e7/sigma;
  - Wilson's pipeline switched to it in 2018-09 ("SXW NIST new scan
    201809" in `wilsonpipeline/four_chunk_gauss_mw.py`).

Method: continuum-normalize both, broaden to R = 80k, then cross-correlate
in 2 nm chunks (58 chunks).

Results:

- **The shift is a smooth ramp.** NIST minus I2_0.1 runs from +632 m/s at
  501 nm down to +16 m/s at 614 nm (median 283 m/s).
- **The ramp is air dispersion.** It matches (n_air(lambda) - n_air(614 nm))
  * c from the standard-air formula: 647, 537, 433, 336, 243, 158, 76, 0 m/s
  predicted against 632, 537, 430, 341, 263, 174, 91, 16 m/s measured.
- **Which file is wrong:** I2_0.1 was most likely converted between air and
  vacuum with a constant (non-dispersive) index, so its wavelength scale is
  off by about +/- 300 m/s, a smooth function of wavelength.
- **Why the RV fit doesn't see it:**
  - across one order the error changes by only ~20-30 m/s;
  - the per-order wavelength offset and slope absorb it, which is probably
    why "neither atlas seemed better" in RVs.
- **It still touches two things:**
  - the per-(telescope, order) velocity offsets;
  - any model that shares a wavelength solution across orders (the optical
    model).
- **Line depths:** the optical-depth ratio NIST/I2_0.1 is 1.05 (p10-p90
  1.04-1.075). Since the fitted iodine strength absorbs this, the two are
  consistent with a cell-temperature or column difference.
- **Shape residual:** after shift and scale, 0.6% rms at R = 80k, against a
  line-depth rms of 7.7%. This is an ~8% shape disagreement and is
  unexplained (FTS resolution or line shape, noise, or temperature). A
  data-driven iodine correction would arbitrate it.

Next: use the NIST scan as the wavelength reference. Test both atlases
chunk by chunk on B-star iodine frames (lower chi2 per chunk), and in the
learned observer-frame residual test.

## 2026-11-21: Re-extracting pre-mid-2018 with v1.0.0 (branch reextract)

v1.0.0 runs on radish (Python 2.7 env on /pool) and reproduces the archived
v1.0.0 products (7 frames from 2018-10/11: flux ratio 0.9999-1.0000,
per-pixel scatter 0.02-0.04 sigma, identical wavelength HDU). Changes:
paths and I/O, plus a mathematically identical diagonal shortcut in
`chi_fit` (2.3x faster, <= 8e-8 sigma). Fallbacks, all flagged in headers:
a 2016 trace file from v1.0.0's own `trace_fitter` (T4 rebuilt from T2/T3
spacing), the no-slit-flat path for 2016 (saturated slit flats), and the
nearest night's bias for 52 nights. v1.0.0 uses the n20161123 wavelength
solution for everything (no ThAr frames exist).

Coverage: 553 of 555 star frames (tau Cet, HD 122064, 51 Peg) and all 187
daytime frames. 2 crash (a trace runs off the chip). 21 faint HD 122064
exposures (mostly Feb-Apr 2018, T3 only) fall below the RV code's 150-count
floor because v1.0.0 removes ~140 counts of blue background; 8 exposures
are recovered. The stale wavelength problem is gone: Dec 2016-Feb 2017
offsets are +0.6 px with no preshift, against -69.7 px (44 of 46 patched).

L0 RVs, same exposures (rms / nightly / within-night, m/s):

| Set | Original | v1.0.0 |
|---|---|---|
| tau Cet, pre-2018 span (80) | 5.66 / 6.08 / 3.14 | 7.92 / 6.89 / 9.23 |
| tau Cet, all years (331) | 4.60 / 4.63 / 2.89 | 5.33 / 4.93 / 4.85 |
| HD 122064 (187) | 5.86 / 5.62 / 5.25 | 5.93 / 6.00 / 4.09 |
| Wilson+19 window (22) | 8.95 / 9.12 / 6.31 | 8.05 / 7.49 / 7.36 |
| 51 Peg K (16) | 54.3 +/- 2.0 | 53.1 +/- 2.2 |

- Bright-star RVs change by only ~1.2 m/s per exposure. The tau Cet
  within-night loss comes from a few faint 2017 exposures moving 10-30 m/s.
- Per telescope, T2 improves (HD 122064 nightly 9.0 -> 3.2) while T1 and T3
  get worse; the combined RMS doesn't improve.
- Era steps barely move: 2016-11-22 is 9.6 +/- 1.3 -> 8.5 +/- 1.5;
  2017-10-02 is -1.3 -> -2.5 (+/- ~1.5).
- Fitted LSF widths shift by -0.009 km/s, below the 0.02 threshold for
  rebuilding the B-star LSF map.
- **Count-level bias is not the extraction:** the tau Cet T2 slope with
  log counts (+6.6 +/- 0.6 m/s per dex) exists only in post-2018-07 data,
  which was always v1.0.0. Pre-2018 data shows ~0 slope with either
  extraction (HD 122064: all telescopes within +/- 2). Caveat: tau Cet has
  only 15-17 pre-2018 T2 exposures.
- **Daytime sky:** the extraction changes the answer (per-order velocity
  fingerprint changes by 17.8 m/s rms per telescope and order; day means
  shift -3 to -22 m/s; New Year day-to-day rms 27.0 -> 20.8 m/s), but
  v1.0.0 extracts these frames badly: its Gaussian profile gives reduced
  chi2 ~ 37 at daytime signal levels and cosmic-ray rejection flags
  profile pixels in 20-80% of columns. (The "27% low flux" was wrong:
  the original daytime extraction is itself 1.22-1.26x the raw box sum;
  see the extract2 entry.) Any redo should use
  a better extractor, not v1.0.0 (one-off in the test bed; out of scope for
  specfast).

Verdict: don't reprocess the archive with v1.0.0. It fixes the stale
wavelength (already handled by the preshift) but loses faint frames and
doesn't improve bright ones. A full redo would be ~10,000 frames, ~430
CPU-h and ~190 GB from the archive. Keep these products as an alternative
for the two stars; wait for specfast's extraction (see DESIGN "Extraction").

Originals verified unchanged (sha256 of 1,423 local files; size, mtime and
inode of 741 archive files). Products and README:
`/pool/radish1/minerva-rv/data/reextract_v1/`; RV results:
`work/results/reextract/`; Charlie branch `reextract` (f35bb48, 8595a84).

## 2026-11-22: Iodine atlas and learned observer-frame correction (branch iodine)

Baseline: L0 (frozen B-star sigma, telluric mask 0.98, two-star
zero-points); the I2_0.1 run reproduces the telluric M98 run exactly.

**Atlas choice (nightly rms / within-night / excess, m/s):**

| | tau Cet | sigma Dra |
|---|---|---|
| I2_0.1 | 4.61 / 2.88 / 2.61 | 11.18 / 5.40 / 9.71 |
| NIST 2018-08 | 4.88 / 3.04 / 3.00 | 11.15 / 5.22 / 9.64 |
| I2_0.1, dispersion-corrected | 4.73 / 2.91 / 2.84 | 11.14 / 5.31 / 9.42 |

- **RVs: a wash.** Swapping atlases moves nightly RVs by 0.8-1.8 m/s rms,
  uncorrelated; tau Cet's 4.61 -> 4.88 is just that added noise.
- **Fit quality favours NIST.** Star chunk chi2_r is ~2% lower. On B-star
  frames (1,821 traces) total chi2 is 3.5% lower and 64% of traces
  improve. The gain is all redward of ~5650 A (13-20% near 5700 and above
  6000 A); a few blue bands are 2-6% worse.
- **Depth:** the NIST/I2_0.1 depth ratio rises from 1.03 to 1.18 toward the
  red, so it is not one column factor. The fitted strength absorbs it
  (0.96-0.97). The B-star sigma is 1% larger with NIST.
- **The per-(telescope, order) offsets are the I2_0.1 dispersion error.**
  They fall from ~210 to 42-60 m/s rms with either NIST or the
  ramp-corrected I2_0.1, and the change per order follows the air ramp
  (+620 m/s in order 1 to ~0 in order 23). The per-telescope part is only
  ~3 m/s. What remains is a 41-59 m/s order pattern, correlated between
  stars (r 0.64; possibly the DSST templates' own wavelength tilt,
  untested), plus 13-25 m/s per (telescope, order). Measured NIST - I2_0.1
  = 0.95 x Ciddor ramp + 23 m/s (10 m/s rms). Era zero-points unchanged.

**Learned static observer-frame correction (Wobble-style, all 7 standards,
each star's rest-frame part removed):**

- **The structure is real:** 0.7-3.7% rms per order. It reproduces between
  disjoint star sets (r 0.97-1.00) and between telescopes (0.90-0.98).
  Across the 2016-11 remount it stays coherent in observed wavelength
  (r 0.87-0.97) but not in pixels (0.2-0.8), so it lives in the wavelength
  frame.
- **Composition:** about half is smooth 10-20 A wiggles (~1.0% rms),
  continuum or blaze shape the quadratic continuum can't follow. About
  half is at line scale (~0.8%), largely common to both atlases, so model
  error (likely LSF shape) rather than atlas choice; NIST leaves less of
  it in the red.
- **Regression:** a water term is significant only in water-rich orders
  and tracks the telluric branch's water column (r 0.98); dry airmass is
  not significant.
- **Hold-out** (learned on 5 stars, applied to tau Cet and sigma Dra):
  per-trace chi2_r halves (tau Cet 4.84 -> 2.41) and formal errors shrink
  25-30%, but nightly RVs barely move. tau Cet goes 4.88 -> 4.71 (excess
  3.00 -> 1.92) and sigma Dra 11.15 -> 10.85; the paired variance changes
  are ~1 sigma. T1 gets worse on both stars, and a per-telescope
  correction is clearly worse (6.55; not investigated).
- **Injection-recovery:** with a 5 m/s 1-yr signal phased with BC, the
  correction absorbs 0.6% (~0.03 m/s). Even uncorrected the chain
  recovers only 96.5% of K at both 1 yr and 47.3 d; that scale loss is
  untraced.

Verdict: use the NIST scan as the reference atlas. A learned
observer-frame correction is safe but buys no RV precision here; fix the
continuum model first. The line-scale residual points at the LSF shape.

Code: Charlie branch `iodine` (36b7499..a0afc5b, local). Atlases:
`work/calib_data/I2_NIST201808_vac.fits`, `I2_0.1_dispcorr.fits`. Results:
`work/results/iodine/`; plots `work/plots/iodine/`.

## 2026-11-22: Tellurics (branch telluric)

Stars: tau Cet and sigma Dra, L0 (frozen B-star LSF), two-star zero-points.
HD 122064 not run.

**Mask threshold doesn't matter.** tau Cet nightly rms / common excess
(m/s) at atlas-T thresholds: 0.95 4.68 / 2.76; 0.98 4.61 / 2.61;
0.99 4.55 / 2.53; 0.995 4.61 / 2.21; no mask 4.54 / 2.66. At 0.999 it
masks 42% of pixels (the atlas noise floor) and degrades to 8.66.
sigma Dra: 10.8-11.7 nightly across the same ladder. BC correlation
r <= 0.14 everywhere; the structure function is the same at all lags.

- Masked pixels at 0.98: 1.2% overall; orders 18 / 19 / 20 (590 nm water
  band) 7.6 / 12 / 3.3%; most orders 0%.
- Only orders 18-20 respond (order-relative nightly rms 30 / 32 / 23 m/s
  for tau Cet against a clean-order median of 18.5). Unmasked, order 19
  doubles, but the joint fit down-weights it, so the combined RV doesn't
  suffer.
- The mask is static (atlas T < 0.98 -> err = inf on the observed-frame
  grid; `fit_order.TELL_THRESH`); it doesn't scale with water or airmass.

**The common mode isn't telluric.** A per-exposure spectral water column
(fitted per trace, shared across orders and telescopes) tracks surface
absolute humidity at r = 0.57-0.64 per exposure and 0.77-0.83 nightly, so
it works as a PWV proxy. The common-mode nightly residual is uncorrelated
with airmass, BC, water column, dew point and humidity (all |r| <= 0.10,
<= 0.13 in-season). In sigma Dra, the per-order residual-vs-water slope
scales with the order's water depth (r 0.80 across orders).

**Fitted telluric model (atlas^a, shared column) is worse than a mask:**
tau Cet nightly 6.19, sqrt(chi2_r) 2.23, BC slope +0.26 m/s per km/s.

- Clean-template test (atlas set to 1 where T > 0.99; 120 tau Cet
  exposures): in the clean orders 4-13 the BC-correlated error drops from a
  median slope of +0.27 to +0.004 m/s per km/s. So the raw atlas's
  0.1-0.3% noise, raised to the fitted power, made fixed features the star
  sweeps across with BC.
- The water orders are unchanged by cleaning (order 18 slope +2.7, order 19
  +2.0 m/s per km/s): one scaled column, with line shapes fixed by the
  atlas, is not a good enough water model at MINERVA's resolution.
- Subset combined nightly rms: mask 0.98 4.76, no mask 4.55, raw model
  6.03, clean model with shared column 4.65 (still BC-correlated through
  orders 18-19). Matches the mask; doesn't beat it.

**CAMAL** (archived data, 154 nights 2017-05..2018-06; 780 /
823 / 860 nm photometry): as reduced (every 15th triplet, per-star
Langley), its water index correlates only r ~ 0.3 with the spectral column
and surface humidity on 21 overlap nights. The spectral column is the
better proxy.

**Correction (2026-11-24): this was our own crude reduction of CAMAL's raw
images, not CAMAL's product.** We copied raw CAMAL frames from the
observatory archive and did our own aperture photometry on every 15th
780/823/860 nm triplet, with a per-star Langley fit and our own water
index; we never used the CAMAL team's PWV, which is calibrated against
GPS (CAMAL PI, via JDE). So the r ~ 0.3 measures our reduction, not
CAMAL, and "the spectral column is the better proxy" is withdrawn. The
PI also notes that PWV decorrelates faster than one might think (so
matching must be close in time) and that the water lines in the iodine
region are tiny, so the spectral column is noisy. Consequence: the null
result "the common mode is uncorrelated with water column" used a noisy
proxy and is weaker than stated; redo it with CAMAL's calibrated PWV,
time-matched per exposure.

Verdict: keep a static mask at 0.98-0.99; treat orders 18-20 specially;
no fitted atlas-power model; keep the spectral water column as a
diagnostic. Tellurics don't explain the shared 2-3 m/s.

Code: Charlie branch `telluric` (local; `drivers/run_telluric.py` now
resumable). Results: `work/results/telluric/`; CAMAL photometry:
`data/camal/`.

## 2026-11-22: Extraction pilot "x2" (branch extract2)

Prototype extractor:
- empirical per-trace profiles (flat-relative optimal extraction), fitted
  jointly per column;
- a 2D scattered-light model;
- per-exposure trace re-centring and width;
- cosmic-ray rejection against the model;
- an honest variance model, with no zeroed windows.

Fibre flats exist only for 2016-01 and 2016-11, so most eras use profiles
stacked from bright frames, chosen by held-out chi2 (1.15-2.1 against
1.3-12 for Gaussians).

**Verdict: don't re-extract the archive for bright-star RVs.** It fails
JDE's rule (> 1 m/s nightly gain, or the T2 slope disappearing). Use the
extractor in specfast for faint targets and diagnostics.

Same exposures (rms / nightly / within-night, m/s):

| Set | original | v1.0.0 | x2 |
|---|---|---|---|
| tau Cet pre-2018 (80) | 5.65 / 6.07 / 3.08 | 7.93 / 6.86 / 9.28 | 5.94 / 6.19 / 4.07 |
| tau Cet post-2018 (103; original = v1.0.0) | 3.77 / 3.79 / 2.18 | same | 3.64 / 3.65 / 2.17 |
| HD 122064 pre-2018 (187) | 5.85 / 5.61 / 5.24 | 5.93 / 5.99 / 4.09 | 5.41 / 5.21 / 3.87 |
| 51 Peg K | 54.3 +/- 2.0 (rms 4.8) | 53.1 +/- 2.2 (5.0) | 55.0 +/- 1.7 (3.9) |

- **Coverage:** all 658 star frames extract, including the 2 that crashed
  v1.0.0. 9 of the 21 faint HD 122064 frames that v1.0.0 lost come back.
- **Per telescope:** T2 pre-2018 improves (tau Cet nightly 15.8 -> 3.2;
  HD 122064 9.0 -> 3.8).
- **tau Cet common excess:** pre-2018 0.0 (original) / 4.4 (v1.0.0) / 2.4
  (x2); post-2018 3.4 -> 3.6. Not an extraction effect.
- **Ablation (tau Cet):**
  - empirical profile: -0.75 m/s nightly pre-2018, ~0 post-2018;
  - 2D scattered light: combined RV about the same, but per-telescope
    results collapse without it (T2 pre-2018 3.2 -> 15.8, T3 post-2018
    6.1 -> 20.5);
  - per-trace re-centring is essential (without it, nightly 8.9 pre-2018
    and 7.2 post-2018).
- **T2 count slope is not the extractor:** +10.2 +/- 0.9 m/s/dex
  (original) vs +10.4 +/- 0.9 (x2) on the same 103 post-2018 exposures.
  It is concentrated in Jul-Dec 2018 (+14 +/- 5); after the 2018-12-22 T2
  throughput jump it is +3.9 +/- 0.9, and profile width adds nothing. No
  sign of nonlinearity: profile width is flat with counts to < 0.5%/dex
  within seasons (no multi-level flat series exists for a direct test).
- **Diagnostics:** width, centroid and background fraction don't predict
  RV residuals (|r| < 0.4, < 1.5 m/s per sigma), except the T2
  counts/epoch confound above.
- **Daytime frames are now sane:** profile chi2_r 8.2 (v1.0.0 ~37);
  cosmic-ray flags in 3.4% of columns (v1.0.0 35%, up to 74%); flux 1.9%
  above v1.0.0. Correction: both are 0.80x the original daytime
  extraction because the original is 1.22-1.26x the raw box sum (a
  normalization difference, not lost flux).

**Calibrations (darks and slit flats; JDE asked to verify the early
conclusion that they add more noise than signal):**

- **Darks: don't use. Confirmed.** Dark current is 0.7-1.1 e-/px per
  900 s, smooth, with no persistent hot pixels; read noise is 3.9 e- and
  scattered light under the traces is 2.8 e-/px. The 2D background absorbs
  the dark level. A master from 5 x 300 s scaled to 1800 s carries
  ~15 e-/px of noise: it roughly doubles pre-2018 bright-star rms and cuts
  the faint survivors from 9 to 2.
- **Slit flats: confirmed for nightly flats; use only a stacked one.** The
  true pixel response varies by 0.39%. A nightly 3-frame master has
  0.42%/px noise, so dividing adds as much as it removes. 17-35-night
  stacks with the illumination divided out reach 0.07-0.16%. Science
  peak-pixel noise is 1.6% (tau Cet), 28% (faint) and 0.6% (daytime), so a
  stacked flat matters only for bright and daytime frames. On 31 tau Cet
  nights the three flat options agree within ~0.1 m/s. 2016 slit flats
  show no pixel signal; 2020-22 has none usable and nothing exists after
  2022, so those epochs borrow the 2018-19 stack.

Full-run cost if ever wanted: ~10,000 frames; ~64 CPU-h extraction (22 s
per frame against v1.0.0's ~155 s) plus ~42 CPU-h of L0 fits; ~190 GB
streamed from the archive (~18 h); ~73 GB of products; ~1 day of wall time
at 8 processes.

Code: Charlie branch `extract2` (ee8441b..4e256fd, local). Data:
`/pool/radish1/minerva-rv/data/extract2/` (README); results:
`work/results/extract2/` (README has every table). Originals verified by
sha256.

## 2026-11-22: extract2 refinement round, frozen as x2-0.2

- **The 12 still-lost faint HD 122064 frames:** 11 were dropped silently
  by the RV code's 150-count floor (T3 only; 112-144 e-/column, S/N 300-430
  per trace). 1 failed on a singular column in the joint solve (fixed).
  With the floor removed and honest-error weighting, all 12 are usable:
  13-17 of 23 orders pass, errors 18-24 m/s, residual/sigma rms 1.15, none
  beyond 3 sigma, and the other 227 exposures move by 0.00 m/s. They must be
  used weighted (unweighted rms rises 6.0 -> 7.9).
- **Daytime profiles:** per-era daytime profiles (16 column blocks, 0.33 px
  knots) bring daytime chi2_r 8.2 -> 3.5 and cosmic-ray flags 3.4% ->
  0.12%. Star frames are unaffected.
- **Stacked pixel-to-pixel flat** is the default (2016 and 2020+ borrow
  the 2018-19 stack, flagged).
- **No regression on bright stars:** tau Cet pre-2018 nightly 6.08 vs
  6.07 for the original.
- **A 2018-07 era break** helps nobody consistently; not adopted.

Frozen as tag x2-0.2 (Charlie branch extract2, 0d548b9). The full
pre-mid-2018 run started 2026-11-22: 10,435 frames over 501 nights, to
`/pool/radish1/minerva-rv/data/extract2/full/`, with a manifest and failure
log.

### Full run result (2026-11-23)

- **Frames:** 10,433 of 10,435 pre-2018-07 frames extracted (5,341
  daytime, 5,092 stellar). The 2 failures are bad raw files in the archive
  (n20171027.daytimeSkyExpmeter.0032 is 0 bytes; n20170410.HD97601.0024 has
  no FITS header). Flagged: 1,454 nearest-night biases, 2016 frames on the
  2018-19 flat stack, 1,442 frames with all four telescopes dark.
- **Cost:** ~17 h wall (archive transfer 0.6-2 MB/s), ~105 GB streamed,
  ~22 s CPU per frame, 48 GB of products.
- **Faint frames:** with the 150-count floor removed, all 21 HD 122064
  frames v1.0.0 lost come back (288 exposures vs 213 original). The 60
  additions have median error 49 m/s and rms z 1.12, so they are honest.
- **L0 vs original, same exposures (m/s):**

  | Set | Original | x2-0.2 |
  |---|---|---|
  | tau Cet pre-2018, all 80: rms / nightly / within | 5.65 / 6.07 / 3.08 | 7.42 / 8.24 / 4.42 |
  | tau Cet pre-2018, err < 6 (68): rms / nightly / weighted / sqrt(chi2_r) | 3.61 / 3.24 / 3.12 / 1.23 | 3.41 / 3.01 / 2.89 / 1.13 |
  | HD 122064, all 187: rms / nightly / within | 5.85 / 5.61 / 5.24 | 4.94 / 4.68 / 3.54 |
  | HD 122064, err < 6 (168): rms / nightly | 4.26 / 3.92 | 4.56 / 4.19 |
  | 51 Peg K / residual rms | 54.3 +/- 2.0 / 4.8 | 55.2 +/- 1.7 / 3.8 |

  The tau Cet all-exposure row is one exposure (n20170929.0010, error 33
  m/s, moves +47 m/s). Bright exposures move a few tenths of a m/s; the
  gains are faint frames and robustness, as the pilot said.
- **Bias:** the mean of 479 nightly bias masters has no 2D structure (0.09
  ADU rms), so the nightly 3-frame master only adds ~2.7 ADU (3.5 e-) of
  pixel noise. A stacked bias (or overscan only) removes the n20170929
  outlier (tau Cet all-exposure rms 7.42 -> 5.62, nightly 8.24 -> 6.15),
  bright frames unchanged. Same pattern as darks and nightly flats. Not in
  the full products (x2-0.3 would be another ~17 h).
- Coverage note: only pre-2018-07 frames were re-extracted; later data are
  still the original v1.0.0 products.
- Products: `/pool/radish1/minerva-rv/data/extract2/full/` (manifest,
  failures, run log); results `work/results/extract2/`; code Charlie branch
  `extract2` (e69a5cd, local). `reextract_v1/raw/` deleted; originals'
  checksums re-verified.

### x2-0.4: detector fixes, validated (2026-11-23)

Tag x2-0.4 (testbed commit 062e8b2). The partial x2-0.3 tree was deleted;
only its manifest and logs are kept.

Fixes:
- Saturation is flagged at 62,000 ADU raw.
- Bias comes from the overscan (first 6 columns skipped, saturated or
  bleeding rows rejected), with an era level where no overscan is usable.
- Read noise is fixed at 2.85 ADU (4.8 in 2016-03-22..04-01) and gain at
  1.265.
- The raw layout is read from the data shape; every odd layout and the
  camera-native frames were tested end to end.
- Warm-CCD frames are extracted but flagged.
- The 2016 nightly pixel flats are saturated and are dropped; 2016 frames
  use the 2018-19 stack.
- Two post-2018 profiles had dry-run or warm-CCD inputs and were rebuilt
  without them.

Validation on 555 frames (L0):

| | x2-0.4 | x2-0.3 | Original extraction |
|---|---|---|---|
| tau Cet rms / nightly / sqrt(chi2_r) (error < 6 m/s, 68 exposures) | 3.44 / 3.10 / 1.14 | 3.43 / 3.11 / 1.14 | 3.61 / 3.24 / 1.23 |
| HD 122064 faint pull (6-15 m/s class) | 1.15 | 1.15 | 1.58 |

- HD 122064 bright frames are unchanged.
- The fixes did not move the faint pulls measurably closer to 1, within
  the scatter of 12-18 exposures.
- 51 Peg K = 55.3 +- 1.7 m/s.

The fixes matter for correctness (saturation, read noise, odd layouts),
not for bright-star precision. Robofast dry runs (from n20261108) are
excluded by date and listed in the manifest with a reason. The
whole-archive run is in progress: pre-2018 first, then 11,302 post-2018
frames.

## 2026-11-23: Per-telescope era breaks from the data (testbed branch telbreaks)

Asked: which per-telescope breaks do the data support? Method: one row per
(exposure, telescope) from flux, header fibre positions, x2-0.2 trace
diagnostics, LSF width/h3, FAU guide offset and star size, and
per-telescope RV deviations for 8 standards. A changepoint search (BIC,
bootstrap dates) proposed candidates. It finds ~0.5 false breaks per series
on synthetic episodic noise, so only breaks where several quantities agree
were kept. The deciding test was the RV chain (L0, joint_fit, common-mode
zero-points) with per-telescope eras or exclusions, in 23 variants.

Base nightly rms: tau Cet / sigma Dra / HD 122064 = 4.63 / 11.24 / 9.23 m/s.

| Break | What steps | RV result |
|---|---|---|
| **2018-12-17, T2 + T3** (site trip; no data 12-15..19) | T2 relative throughput +1.3 dex, LSF width +1.5%, h3 +0.008, FAU star size -2.1", RV +10.6 m/s; T3 throughput -0.37 dex, RV -3.7 | **4.46 / 11.01 / 8.82** (best). T2 alone 4.42 / 11.09 / 9.05; all four telescopes 4.69 / 11.05 / 8.83 (T1, T4 only react to T2) |
| 2018-07-01, T3 | - | 4.86 / 11.22 / 9.02: worse. Drop |
| 2019-09-18 per telescope | - | No gain over the instrument-wide era. Keep instrument-wide only |
| T2 2019-05-08..07-14 | star 7-11" off the fibre, throughput -1.3 dex | As an era: worse. **As an exclusion: sigma Dra 10.98, within-night rms 5.37 -> 4.70** |
| T2 2018-10-29..12-14 | RV -12.6 m/s (known mis-guiding) | Era or exclusion: no gain. Flag |
| T3 2019-11-05..12-04 | throughput -0.7 dex, RV -5 then +6 | Era: no gain. Flag (exclusion untested) |
| 2019-10-20, all | LSF width +0.9% (end of the excluded window) | Covered by the common-mode zero-point |
| T3 2017-12-16, T4 2017-03-08 | LSF width -3.6% / -1.8% | No gain |

- The 2018-12-22 date was wrong: nights 12-20 and 12-21 are already in the
  new state. It made no difference here only because the three test stars
  have no RVs on those nights.
- T2's 2017-10..2018-12 deficit (~10x fainter in starlight) was the
  telescope feed, not the fibre: daytime sky shows only a 0.06-0.3 dex
  deficit. The trip fixed it. The ZWO guide cameras went in on that trip:
  header fibre positions change units on 2018-12-20.
- The 2025-11 T1/T2 LSF step is the 2024-03-15 instrument era seen late (no
  T1/T2 data 2022-11..2025-11). Some cross-dispersion steps coincide with
  x2 profile-era boundaries, so they are extraction artefacts.
- No 2015 era is needed: the archive starts 2016-01-15, and the first star
  frames are on 2016-01-29.
- Limits: only tau Cet, sigma Dra and HD 122064 were tested, and the last two
  end in early 2020, so post-2020 per-telescope breaks are untestable. Static
  h3 at the 2018-12-17 break (T2 h3 +0.008) is plausible but untested.

## 2026-11-22: Fibre feed (JDE) and what it implies

Each telescope feeds an octagonal fibre butt-coupled to a circular fibre.
(As designed, Bottom et al. 2014, SPIE 9147, 91472E: 50 um octagonal
fibres, 2.3 arcsec on the sky, fed directly at the telescope's f/6.6 with
no focal-ratio conversion; closed-loop guiding at ~0.2 arcsec rms, i.e.
~9% of the fibre diameter; no mode scrambler or agitator is described.)
Light travels in the octagonal leg's cladding as well as its core, and the
circular fibre's core cuts part of that cladding light at the joint.

How the input could reach the LSF and the counts:

- How much light goes into high-angle and cladding modes of the
  octagonal leg depends on the input: star centring, seeing, collimation
  and mirror scatter.
- The circular core accepts only part of the cladding light, at the edge
  of its face. So the transmitted flux AND the near- and far-field
  illumination entering the circular leg (which scrambles radially poorly)
  both depend on the input.
- That gives a direct mechanism for:
  - throughput-LSF correlations (h3 vs throughput r 0.2-0.3; vs YFIBER up
    to 0.31);
  - count-dependent RVs (the T2 slope);
  - T2's +2.9% width jump at the 2018-12 trip (cleaning and
    re-collimation changed the input angles).

Tests:

- **Per telescope:** LSF width and h3 against relative throughput and FAU
  guide offset and seeing on ordinary nights.
- **extract2 per-trace diagnostics:** cross-dispersion width and profile
  wings against the same, since cladding light enters at the edge of the
  circular core and should change the output near-field.
- **The T2 count slope:** whether it tracks guide offset and throughput
  deficit rather than counts themselves.

specfast implication: the LSF can't be fixed per telescope; it needs a
regularized dependence on the fibre-feed state (throughput deficit, guide
offset, profile shape). Hardware note for later: a cladding-mode stripper
on the octagonal leg ahead of the joint would remove the input-dependent
cladding light.

### Interim results (branch feed, 2026-11-22; tests 1, 3, 4; test 2 pilot only)

Outputs: `work/results/feed/`. Feed proxies tried: own relative throughput
`lthru` (clouds removed), cloud-driven counts `lcom`, FAU guide offset,
jitter, FAU half-flux radius, autofocus HFR. Partials take out era,
airmass and time; three stars pooled.

- **LSF vs feed state.** Throughput tracks the LSF; guide offset and seeing
  don't (all |r| <= 0.2, and they explain little of throughput itself).
  - Width scale vs `lthru`: T3 r = -0.47 (z 10.5, -1.7%/dex, same within a
    night), T4 -0.29, T1 -0.18, T2 ~0 (sign flips by era).
  - It is the feed, not S/N: on T3 `lthru` gives -2.05 +/- 0.25%/dex and
    `lcom` -0.25 +/- 0.20. T1/T4 are mixed.
  - h3 vs `lthru`: T2 r = +0.34 (z 7); other telescopes ~0.
  - Leave-one-star-out width prediction: r 0.56-0.76 on T3 before
    2018-12-22, 0.1-0.5 after.
- **Cross-dispersion (pilot).** Profile halo at 3-7 px vs `lthru`: T3 r =
  -0.46, T2 -0.39. The cross-dispersion width tracks the spectral LSF width
  (r 0.62 T1, 0.64 T3, 0.39 T2/T4). Near field and LSF move together, as
  the feed mechanism predicts.
- **T2 count slope.**
  - Jul-Dec 2018: counts were a proxy for throughput. With `lthru` added the
    count slope goes from +6.4 to +0.1 m/s/dex; guide offset carries +17 +/- 6
    m/s per arcsec (the Oct-Nov 2018 mis-guided episode).
  - After 2018-12-22: not the feed. tau Cet +3.5 +/- 0.6 m/s/dex barely moves
    with feed regressors, and clouds give the same slope as own throughput,
    so it is a count-level (S/N) effect. Per-exposure fitted width + h3
    remove it (+0.7 +/- 0.5), but fitted h3 is partly circular.
- **Payoff (fixed-kernel refits; nightly rms m/s, tau Cet / sigma Dra / HD 122064).**

  | Model | tau Cet | sigma Dra | HD 122064 |
  |---|---|---|---|
  | L0 (production) | 4.63 | 11.24 | 9.23 |
  | S1 free width | 4.57 | 11.21 | 9.36 |
  | S3 free h3 | 4.50 | 11.17 | 8.07 |
  | F1 feed-predicted width | 4.65 | 11.18 | 9.37 |
  | F2 feed-predicted width + h3 | 4.45 | 11.26 | 9.10 |

  - A predicted width does nothing (F1 = L0): width moves v by < 1 m/s.
  - Predicted h3 adds no within-night noise (free h3 does: tau Cet 3.11 vs
    2.89), but gains only 0-4% nightly. F2 cuts the post-trip T2 count
    slope on sigma Dra from +6.1 to +1.3 m/s/dex.

**Correction (same day): F2's gain is static per-era h3, not the feed state.**
Control F2i keeps only F2's intercepts (one width scale and one h3 offset
per star, tel and feed era; no per-exposure variation): nightly 4.46 /
11.08 / 9.00 (tau Cet total 4.32 vs F2 4.36, L0 4.60). The per-exposure
feed part adds +0.0 / +0.18 / +0.10 m/s. Ablations agree: h3 from
throughput/fibre position/airmass (F2t) 4.46 / 11.24 / 9.09; h3 from
cloud counts only (F2c) 4.43 / 11.22 / 9.11. The per-exposure part only
cancels the post-trip sigma Dra T2 count slope (+5.6 -> +1.3 m/s/dex), and
that needs h3 tracking total counts, consistent with a count-level effect.
Caveat: the feed eras add breaks at 2018-07-01, 2018-12-22 and 2019-09-18,
where joint_fit has no per-telescope zero-point, so the per-(tel, era) h3
may just be acting as a per-tel offset (cf. freelsf: static h3 shrinks the
era steps).

Conclusion: the feed mechanism is real (throughput, LSF width, T2 h3 and
the near field move together), but a feed-constrained per-exposure LSF does
not beat L0.

**Zero-points vs static h3** (extra per-(tel, order, era) offsets in
joint_fit at 2018-07-01, 2018-12-22 and 2019-09-18; `work/results/feed/lsfpred_z/`).
Nightly / total rms m/s:

| Model | tau Cet | sigma Dra | HD 122064 | Z step 2019-09-18 |
|---|---|---|---|---|
| L0 | 4.63 / 4.60 | 11.24 / 9.65 | 9.23 / 8.51 | 11.48 |
| L0 + ZP | 4.78 / 4.60 | 11.08 / 9.57 | 8.80 / 8.22 | 11.11 |
| F2i (static h3 per era) | 4.46 / 4.32 | 11.08 / 9.53 | 9.00 / 8.49 | 8.87 |
| F2i + ZP | 4.67 / 4.44 | 10.92 / 9.45 | 8.69 / 8.26 | 8.94 |

- sigma Dra and HD 122064: zero-points alone give all of F2i's gain or
  more, so there it is per-tel era offsets.
- tau Cet: zero-points hurt; static h3 helps, so it changes the per-order
  velocities, not just their offset. Static h3 alone absorbs ~2.6 m/s of the
  2019-09-18 common-mode step (zero-points don't).
- T2's post-trip count slope is unchanged by zero-points.
- Every variant is within ~5% of L0. None of the gain is per-exposure feed
  state.

specfast: allow per-telescope offsets at the 2018-07-01, 2018-12-22 and
2019-09-18 breaks, and a static per-(tel, era) h3; test both on all
standards.

**Test 2 on the full re-extraction** (216 of 501 nights, 1,627 exposure-tel
rows; re-run when the full run completes): cross-dispersion core width
tracks the spectral LSF width on every telescope (r 0.52-0.61, within-night
0.35-0.62). Cross-dispersion width vs own throughput: T3 -1.6 +/- 0.35%/dex
(clouds +0.3, a feed effect), T2 -1.2 (clouds -0.44, partly), T4 -1.0
(clouds -0.84, mostly counts). Halo at 3-7 px vs throughput: T2 r = -0.37,
T3 -0.25 (weaker than the pilot's -0.46), T4 opposite sign (+0.28).

**Final verdict (feed thread):** the feed effect is real on T3 (LSF and
near-field width) and T2 (h3), but too small to matter for RV. The post-trip
T2 count slope is a count-level h3 effect, not the feed. Guide offset and
seeing don't predict the LSF. The T3 results still support a cladding-mode
stripper as a hardware fix. Code: Charlie branch `feed` (local); results
`work/results/feed/`, fetched FAU stamp sizes and autofocus records in
`data/feed/`.

## 2026-11-22: LSF width gradient along each order (branch lsfgrad)

JDE's question: the free-LSF tests assumed one width per order. Could the
along-order width variation dominate the exposure-to-exposure variation?
**No.** Results: `work/results/lsfgrad/`. Telescopes 1-based (T1-T4).

- **The gradient is real, large and static.** Width changes by g = -0.05 to
  -0.11 blue to red (+/-3-5% at the order ends), plus significant curvature.
  Its per-(exposure, tel) scatter (0.005-0.015) moves the end widths by only
  0.25-0.75%, against 1-3% scatter in the mean width. Steady night to night,
  no step at 2018-12-22 (T2's mean width jumps +2.9 +/- 0.4% there; its
  gradient moves +0.001 +/- 0.003), no steps at era breaks. It anticorrelates
  with the mean width (r -0.5 to -0.8) and weakly tracks throughput
  (r +0.16 to +0.39); |r| < 0.16 with airmass and fibre position.
- **Two-star ladder (tau Cet + sigma Dra, nightly rms m/s):** L0 4.61 / 11.18;
  static gradient G0 4.62 / 11.05; with curvature 4.62 / 11.06; free width +
  gradient per trace 4.65 / 10.91; one width scale + gradient offset per
  exposure (SG1) 4.57 / 11.09. HD 122064: L0 9.19, G0 9.19, G1 9.47. RVs
  move 0.4-1.1 m/s rms; no variant gains more than ~1%. Only adding h3 (G2)
  moves the era zero-point steps (to ~4 m/s), as freelsf L2 did.
- **The gradient is a tracer, not a cause.** tau Cet T2: r(gradient, RV) =
  -0.48, but SG1 moves the RV the wrong way (r +0.26), and the correlation
  is mostly exposure-level; it tracks throughput/illumination. sigma Dra T1:
  r +0.67, and SG1 does fix it (exposure rms 10.2 -> 7.1, nightly 7.7 -> 6.5),
  but T1's era offsets swamp that in the combined rms. Other telescopes
  |r| <= 0.15.
- **Injection** (tau Cet exposure, noise-free, BC swept +/-30 km/s, fitted
  with constant width): the B-star gradient gives 1.26 m/s peak-to-peak,
  ~0.33 m/s rms combined over orders, jagged in BC with no trend (lines
  sliding through the iodine forest), linear in the gradient (3x: 4.0 m/s
  p-p). Not a smooth annual term; real per-order BC slopes are unchanged.
- **Per-segment structure:** the static per-(tel, order, quarter) rms is
  75.8 m/s without and 75.6 with the gradient. Something else (e.g. the
  +/-0.1 px along-order distortion) makes it.
- Constant-width fits sit 0.08-0.16% below the gradient model's mean
  width; per-(tel, order) offsets move 1.3-1.8 m/s.
- B-star map caveats: order 4 missing (stellar mask); halves/thirds fits
  biased in order 23 and in curvature.

Verdict: keep the constant-width production LSF. If an LSF term is ever
added per exposure, make it h3. Correction: the interim "T1" width jump
and "T1" r = -0.48 were 0-based index 1, i.e. **T2**; fixed above.

## 2026-11-24: Wavelength distortion and the order pattern (branch wavedist)

Test-bed branch `wavedist` (private test-bed repo, commit 1e625de). The
fixed per-era along-order distortion D(p) (from the wavemodel branch) goes
inside the wavelength solution. Variants: quadratic (Q), Q + D, quartic
(R), R + D. Chain: NIST atlas, frozen B-star LSF sigma, telluric mask 0.98,
joint offsets, common-mode era zero-points, original extractions.

**Q1: D(x) improves the fit, not the RVs.** Nightly / within-night /
sqrt(chi2_r), m/s:

| Star | Q | Q + D | R | R + D |
|---|---|---|---|---|
| tau Cet | 4.87 / 3.05 / 1.56 | 4.92 / 2.96 / 1.62 | 5.63 / 3.19 / 1.56 | 5.78 / 3.21 / 1.60 |
| sigma Dra | 11.12 / 5.17 / 1.72 | 11.15 / 5.23 / 1.78 | 10.78 / 5.36 / 1.72 | 10.69 / 5.41 / 1.81 |
| HD 122064 (2016-20, 232 exp.) | 9.18 / 6.49 / 1.36 | 9.16 / 6.49 / 1.37 | 9.02 / 6.85 / 1.28 | 9.06 / 6.67 / 1.31 |

- 51 Peg (16 exposures): K = 54.46 +/- 1.79 (Q), 54.45 +/- 1.53 (Q + D),
  54.67 +/- 1.77 (R), 54.78 +/- 1.64 (R + D) m/s; residual rms 4.22 / 3.64 /
  4.22 / 3.89. With the solar atlas as template: 55.72 / 55.91 +/- 1.97.
- Median per-trace chi2_r relative to Q: Q + D 0.959-0.984, R 0.991-0.997,
  R + D 0.951-0.979. D is worth 4-5x what the quartic buys.
- D moves per-trace velocities by 20-30 m/s rms, but statically per
  (tel, order), so the joint offsets absorb it and exposure RVs do not
  move. The quartic hurts tau Cet (4.87 -> 5.63) and gains nothing else.
- Era zero-point steps (tau Cet + sigma Dra) shrink: 11.7 / 14.0 (Q),
  9.6 / 11.7 (Q + D), 7.2 / 9.1 m/s (R + D). Part of the era steps is
  wavelength-model error.
- Residual pixel-position error common to all tels and orders (tau Cet
  stacks): 0.071 px (Q), 0.037 (Q + D), 0.015 (R + D); stable 2017-18 vs
  2019+ (r 0.98), so one D holds from the remount to 2026. Caveat: the HD
  122064 post-remount stack is inconsistent (0.17 px, uncorrelated between
  periods), possibly the preshift-rescued Dec 2016-Mar 2017 frames; not
  investigated.
- Earlier, under the old I2_0.1 atlas (wavemodel W5, HD 122064, 209
  exposures): Q 10.14, Q + D 10.28, R 9.40 m/s rms. Same conclusion.

**Q2: per-segment structure is real and mostly common to all
telescopes.** Static per-(tel, order, quarter) rms; split-half noise 3-5
m/s, split-half r 0.99-1.00.

| Variant | tau Cet | HD 122064 | sigma Dra |
|---|---|---|---|
| Independent quarters (lsfgrad definition), Q | 76.6 | 120.3 | - |
| Independent quarters, Q + D | 76.7 | 120.3 | - |
| Shared solution, 4 segment velocities, Q | 106.8 | 133.7 | - |
| Shared solution, Q + D | 86.2 | 122.4 | 79.1 |
| Shared solution, R + D | 81.1 | 117.8 | - |

- Reproduces the lsfgrad 75.8 m/s. With independent quarters each
  quarter's own quadratic absorbs D.
- D removes most of the mean segment pattern common to all orders (tau
  Cet [+39, -60, +86, -23] -> [+11, -9, +20, +2] m/s; HD 122064 [+21, -56,
  +79, -32] -> [-0.5, -17, +23, +11]). What remains is order-specific.
- Common to all telescopes: 78-120 m/s; per-telescope remainder 8-21
  m/s (4-8 with independent quarters). Not a per-fibre effect.
- Across stars: common part 76.6, per-star part 60.6 m/s. Pair
  correlations: tau Cet / sigma Dra 0.77 (same Keck template run), sigma
  Dra / HD 122064 0.52, tau Cet / HD 122064 0.18. The star-specific part
  follows the template.
- Stable in time (pre/post remount r 0.87-0.91; 2017-18 vs 2019+ r
  0.97-0.99). Quarter-scale cells cannot tell a 68 px move from a fixed
  position.

**Q3: the 41-59 m/s order pattern is mostly the DSST templates.** Order
pattern = per-order offset after removing a per-(tel, era) mean.

| Star (template run) | Order pattern rms | Per-(tel, order) rms |
|---|---|---|
| tau Cet (rj82) | 59.5 | 12 (noise 13) |
| sigma Dra (rj82) | 40.9 | 5 (noise 4) |
| HD 122064 (rj08) | 105.9 | 17 |
| HD 201091 (rj08) | 73.4 | 13 |
| HD 62613 (rj06) | 82.6 | 5 |
| HD 26965 (rj06) | 71.5 | 4 |
| HD 19373 (rj76) | 123.7 | 16 |

- Same-run pairs correlate at r 0.64 (rj82) and 0.86 (rj06), but the rj08
  pair at -0.02; different-run pairs -0.76 to +0.63.
- Decisive: HD 122064 with template rj08 -> rj122 on the same data changes
  the order pattern by 82 m/s rms, zigzagging order to order with no slope;
  the pattern falls from 106 to 54 m/s (37 after a quadratic in order). The
  per-(tel, order) part does not change.
- 51 Peg DSST vs solar atlas: 90 m/s rms (a +12 m/s per order tilt plus
  44.5 m/s order-to-order scatter).
- Minor: D changes the pattern by 2-6 m/s; atlas choice (NIST vs I2_0.1)
  by 0-5 m/s.
- A floor of ~38 m/s rms common to all 7 stars remains (each star departs
  from it by 25-119 m/s). Unidentified: iodine- or MINERVA-side, possibly
  mixed with convective-shift and line-mix effects.

**Verdict.** D is a real calibration term worth fitting, but neither D nor
the wavelength model's degree causes the nightly scatter. Each DSST
carries per-order (and per-segment) wavelength zero-point errors of 40-100
m/s, common to all telescopes; per-(tel, order) offsets have been absorbing
them all along.

**Design consequence (DESIGN.md "Wavelength" and "Templates"):**
- Per-era calibration products: D(p), common to all orders and fibres,
  re-derived at each optical change; a static per-trace optical-model
  curve as the starting guess and prior.
- Per exposure, per trace: a quadratic in x' = (p + D(p)) / p_med. No
  quartic.
- Nuisance offsets per (template, order), or per (template, order,
  segment) when segments are fitted separately, shared by all telescopes
  and stored with the template, not the instrument. The per-(tel, order)
  remainder is only 5-17 m/s.
- Move to inferred templates on the instrument's own iodine-calibrated
  scale; until then the per-order offsets stay.
- G-CLEF: the comb measures D(p), the per-trace solution and era drifts
  directly, but not the template's wavelength scale. Its templates must be
  built from its own comb-calibrated spectra, or carry per-order template
  offsets. A comb should also show whether the ~38 m/s common floor is
  iodine-side.

## 2026-11-24: G-CLEF extraction modes from simulated frames

Simulation (collaboration-private code and inputs): noise-free raw frames
ray-traced from the G-CLEF optical design with specfast's tracer and a
deterministic linear renderer (PyEchelle's photon renderer is Monte Carlo
only). GMT PRV mode: seven hexagonal science slices plus comb fibres at
the slit ends (the calibration-fibre placement is assumed). Solar
spectrum in the science slices, 25 GHz comb, flats; 512 px chunks of
three blue orders; geometric PSF, optionally plus a scattered-light halo
(2% in 4 px; harsh case 5% in 8 px). RVs from a linearised forward model
against the known spectrum, comparing perturbed with reference frames at
zero injected velocity. Modes: m1 1D simultaneous profile fitting
(per-frame weights); m1f with fixed model weights; m1fc m1f after
subtracting a 2D comb-light model; m2 spectro-perfectionism (m2b:
resolution matrix per fibre); m3 2D forward model.

Results, cm/s, combined over the seven slices:

| Perturbation | m1 | m1fc | m2 | m2b | m3 |
|---|---|---|---|---|---|
| Slice flux tilt 5%, no halo | <= 0.01 | ~0 | 0 | 0 | 0 |
| Slice flux tilt 5%, 2% halo | 0.2-1.2 | 0.5-0.7 | 1.1-1.8 | 0.01 | 0 |
| Comb flux x1.2, 2% halo | -11.7 to +3.8 | 0 | - | <= 0.12 | 0 |
| Star x0.01 (comb unchanged), no halo | -4 to -14 | 0 | 0 | 0 | 0 |
| Star x0.01, 2% halo | 530-2900 | 0 | - | 11-59 | 0 |
| Trace offset 0.01 px across dispersion, cal vs science | -0.9 | | -85 | | -109 |

- Per-frame (Horne) weights make the LSF depend on flux (4-14 cm/s);
  fixed model weights remove it.
- Comb light leaking into the adjacent science slice through PSF wings
  is the largest extraction term; a per-exposure LSF fit does not remove
  it, a 2D comb-light model does (an empty slot between comb and
  science mostly does).
- Mode 1's extracted LSF tracks the true one: centroid within 0.03 m/s,
  width within 6e-4 px of 2.28 px; under 1% illumination gradients it
  follows the true LSF change to 0.2 cm/s.
- Mode 2 needs the trace position across the dispersion to ~1e-3 px per
  fibre and the halo amplitude and width to ~1%; mode 3 needs a perfect
  PSF. Neither is required.
- **Illumination inside a fibre dominates and no mode removes it.** Per
  1% linear near-field gradient: about -6.4 m/s along the dispersion,
  +0.26 m/s along the slit in m1 (1.1 m/s in m2/m3, because the sheared
  fibre image turns an unmodelled cross-dispersion shift into a
  wavelength shift); far-field gradient 0.1-0.7 m/s by order; comb-fibre
  near field alone 0.15-0.4 m/s. A 1% gradient is a centroid shift of
  ~1.4e-3 of the core, so 10 cm/s needs the near-field centroid stable
  to ~2e-5 of the core (scrambling).
- Runtime per arm per exposure, one core: m1 ~1 min; m2 ~1.5 h (in
  patches); m3 10-15 min per fit but ~500 core-hours to build its PSF
  operators per PSF model.

Verdict: mode 1 with fixed weights and 2D comb-light subtraction meets
10 cm/s for extraction; modes 2 and 3 are not needed. G-CLEF's budget is
set by fibre illumination stability, which belongs to the instrument
(scrambling, pupil stability) and to the per-exposure illumination LSF
kernel, not to extraction. Caveats: one 512 px chunk per case (leakage
errors flip sign between orders and partly average); no pixel response,
charge transfer, red arm or sky; mode 2 PSF not estimated from comb
frames, so its requirements are not shown to be achievable. Reusable,
design-free pieces for specfast: the simultaneous column trace fit, a
spectro-perfectionism class with per-fibre R, the linearised
differential RV fit, halo helpers.

## 2026-11-24: Iodine information content and modelling tolerances (testbed branch iodinfo)

Test-bed branch `iodinfo` (private test-bed repo, commit 3ca5715).
Synthetic, noise-free, linear response, one trace: all 23 iodine orders
(503-620 nm, 2048 px), specfast's forward model and the PR #7 template
code, NIST 2018-08 iodine scan, B-star LSF widths, D(p) fixed. Templates:
Kurucz solar atlas, and a K-dwarf proxy (solar depths x1.85). Flat S/N,
no blaze or read noise; BERV averaged over +/-25 km/s.

**Cramer-Rao bound on the exposure RV, per trace (m/s; S/N 100 / 200):**

| Model family | Sun | K dwarf |
|---|---|---|
| Only v free (photon limit) | 1.78 / 0.89 | 1.19 / 0.60 |
| (c) LSF known, wavelength per order | 2.07 / 1.04 | 1.57 / 0.79 |
| (b) LSF smooth across orders, per-exposure h3; any N | 2.24-2.27 / 1.12-1.13 | 1.79-1.81 / 0.90-0.91 |
| (d) as (b), template inferred, N = 30 / 100 / 300 | 2.41 / 2.29 / 2.25 (S/N 100) | 1.93 / 1.83 / 1.81 |
| (a) legacy chunk LSF (sigma, h3, h4) | 2.67 / 1.34 | 2.18 / 1.09 |
| (a) legacy chunk sum of Gaussians | 2.98 / 1.49 | 2.45 / 1.23 |

- The LSF-velocity degeneracy breaks: symmetric LSF terms cost nothing
  once shared across orders; only a per-exposure mean h3 couples to v
  (r -0.32), costing 8% (Sun) to 14% (K dwarf) in sigma. Pooling beyond
  N = 3 adds nothing: 23 orders of iodine already pin the shape.
- Inferring the template costs < 10% more by N ~ 30 with a BERV spread of
  >= +/-5 km/s; within 5% of the known template by N ~ 100.
- Legacy chunk fitting costs 30-45% in sigma: real but not a floor.
- Iodine's information is not the limit: everything but v known is only
  1.2-1.3x better than (b). More orders or bluer light would gain more.

**Sensitivity (bias at plausible error sizes; Sun):**

| Rank | Error | Bias, m/s | Tolerance for 1 m/s / 30 cm/s / 10 cm/s |
|---|---|---|---|
| 1 | LSF h3 change per exposure, 0.01 (if not fitted) | 17.2 | 6e-4 / 1.7e-4 / 6e-5; zero if fitted per exposure |
| 2 | h3 change across orders, 0.01 | 5.1 | 2e-3 / 6e-4 / 2e-4; zero if fitted |
| 3 | Model grid 0.25 km/s with the raw NIST scan | 0.69 | needs ~0.05 km/s grid (or a pre-smoothed atlas) |
| 4 | Template line depths 1% | 0.42-0.46 | 2% / 0.7% / 0.2%; zero with an inferred template |
| 5 | D(p) error, 0.01 px | 0.33 | 0.03 / 0.009 / 0.003 px |
| 6 | Iodine per-feature depth 1% | 0.25 | 4% / 1.2% / 0.4% |
| 7 | Static LSF shape (h3, h4 0.01; width 1%) | 0.14-0.21 | ~0.006 / 0.002 / 0.0006 |
| 8 | Iodine atlas noise 0.3% per sample | 0.18 | 1.7% / 0.5% / 0.17% |
| 9 | Stitching step 0.02 px | 0.14 | 0.15 / 0.044 / 0.015 px |
| 10 | Micro-tellurics (synthetic: 1 line per 2 A, 0.1-1% deep) | 0.09 | 10x / 3x / 1x this population |
| 13 | Detector dx, 3e-3 px rms per edge | 0.05 | 0.057 / 0.017 / 0.006 px |
| 14 | Cell temperature 1 K | 0.001 | negligible |

- An atlas wavelength-scale error only moves the zero point.
- A telluric correction from an atlas's sub-1% structure (noise and solar
  residuals) would inject up to 1.5 m/s: an upper bound, not a
  measurement.

**Verdict (supports JDE's view).** The 0.5-1 m/s floor of iodine
programmes is a modelling limit, chiefly LSF asymmetry (h3) varying per
exposure and template line-depth errors, not iodine's information
content. Attainable per trace at S/N 200: ~1.1 m/s (Sun-like), ~0.9 m/s
(K dwarf); a season of N = 100 averages to ~0.1 m/s photon-limited.
- 1 m/s: fit a per-exposure h3 shared across orders (the measured T2 h3
  jump of 0.008 would otherwise cost ~14 m/s).
- 30 cm/s: also an inferred template, D(p) to 0.01 px, a model grid
  finer than 0.25 km/s, iodine depths to ~1%, static LSF shape pooled to
  ~0.002, stitching to 0.04 px.
- 10 cm/s: at least six terms each held to ~5 cm/s, several of them (D,
  detector dx, static LSF, atlas depths) needing external calibration
  that iodine data alone cannot supply. Not impossible, but not from
  iodine data alone.

Caveats: synthetic and noise-free, one trace, Gaussian LSF as truth,
scaled-solar K dwarf, iodine atlas exactly known in (d). The 0.25 km/s
grid artefact should be checked on real data before sub-30 cm/s work.

## 2026-11-25: Whole-archive re-extraction x2-0.4 (testbed branch extract2)

Every KiwiSpec star, B-star and daytime frame in the observatory archive
through 2026-11-07 is re-extracted with x2-0.4: 21,735 OK, 2 failed (bad
raw files: one empty, one with no FITS header), 582 excluded (robofast
dry runs from 2026-11-08). x2-0.4 = x2-0.2 plus the long-term stacked bias
(479 nights), the kiwispec.yaml detector constants (gain 1.265 e-/ADU,
read noise 2.85 ADU, 4.8 ADU in 2016-03-22..04-01; saturation 62,000 ADU
raw; overscan handling and raw layout read from the data shape; warm-CCD
flag), and post-2018 era profiles. 12,575 frames (2016, and 2020 on) use
the 2018-19 pixel-flat stack because they have no usable slit flats.
Flags carried per frame: 1,031 warm CCD, 1,084 with no usable overscan
(era bias level), 8,426 with a saturated raw pixel, 3,265 with all four
telescopes dark. Cost 158 CPU-h; 100 GB of products.

Same-exposure comparison with the original extraction, same RV code (m/s;
unweighted rms / nightly / within-night):

| set | original | x2-0.4 |
|---|---|---|
| tau Cet pre-2018 (80 exp) | 5.66 / 6.08 / 3.14 | 5.75 / 6.30 / 3.06 |
| tau Cet post-2018 (251) | 4.20 / 3.96 / 2.83 | 4.13 / 4.07 / 2.43 |
| HD 122064 pre-2018 (202) | 6.65 / 7.34 / 5.06 | 5.69 / 6.01 / 3.89 |
| HD 122064 post-2018 (19) | 4.77 / 4.84 / 3.41 | 3.81 / 3.85 / 3.08 |

- Bright exposures are unchanged to about +-0.2 m/s; the gains are on
  faint exposures (HD 122064 pre-2018 nightly 7.34 -> 6.01). The extraction
  is not what limits tau Cet.
- Pulls 0.96-1.30 in every error class. 51 Peg K = 55.3 +- 1.7 (rms 3.9)
  against 54.3 +- 2.0 (rms 4.8). x2 recovers exposures the original lost
  (tau Cet post-2018: 271 vs 251).
- The T2 count-level slope (+8.0 +- 0.6 m/s/dex) survives the new
  extraction, so it is not an extraction artefact.
- Ten of 21 lost HD 122064 frames sit at the RV code's 150-count floor;
  removing the floor and weighting by errors recovers all 21 (an RV-side
  change, not yet made).

## 2026-11-25: NEID tau Ceti through specfast: the stellar floor and the MINERVA overlap

Public NEID L2 (DRP v1.5.2, one master wavelength solution): 132 frames,
2023B (12 nights), 2024B and 2025B (including 11 nights MINERVA also
observed); 124 pass an RV-blind cut on S/N and exposure-meter flux
variability. BERV range +-22 km/s. 2021B (DRP v1.5.3) left out.

specfast infer mode on 18 telluric-light orders (409-639 nm), one
template, L1 wavelengths fixed, one offset per season (segment offsets
split at 2024-03-01, below):

| | specfast | NEID CCF (DRP) |
|---|---|---|
| rms per exposure | 0.73 m/s | 0.86 m/s |
| within-night rms (formal) | 0.51 (0.32) | 0.46 (0.32) |
| rms of nightly means (expected) | 0.61 (0.23) | 0.80 (0.22) |
| night-to-night excess | **0.56** | **0.77** |
| BERV slope | -0.004 m/s per km/s (r -0.07) | -0.016 (r -0.28; ~0.7 m/s across the season) |

The two pipelines differ by 0.63 m/s per exposure (r = 0.69) and 0.55
m/s in nightly means (r = 0.72). The ~0.4 m/s within-night excess in
both is consistent with tau Ceti's p-modes and granulation in 60-110 s
exposures.

- **tau Ceti's stellar night-to-night floor is <= 0.6-0.8 m/s**: the whole
  NEID excess, an upper limit on the star (it includes NEID's own
  instrument and pipeline terms). This replaces the literature estimate
  (~0.7 m/s) with a measurement.
- **MINERVA's excess is not stellar.** On the 11 overlap nights MINERVA's
  nightly means (testbed v5) scatter 3.3 m/s (formal ~2.0; chi2 21 for 11
  nights) and correlate with NEID's at r = +0.08 and with specfast-on-NEID
  at r = -0.03. NEID scatters 0.96 and specfast 0.81 m/s on the same
  nights. Only 11 nights with 1-4 MINERVA exposures each, but a stellar
  signal of MINERVA's excess size (~1.8 m/s) would have shown.
- **Modify mode with the DSST prior** (7 orders, 501-631 nm) agrees with
  infer mode on the same orders to 0.27 m/s rms (formal 0.53), excess
  0.62 m/s. DSST segment zero points span +-100-185 m/s (the known DSST
  zero-point problem); inferred templates avoid it.
- **NEID's "BERV slope" is not a barycentric-correction error.** specfast
  applied NEID's own barycentric correction (z_bary from the L2 header;
  0.08 m/s rms difference from re-applying it), so both pipelines share it
  and it cancels in their difference, yet NEID minus specfast still trends.
  Within each season tau Ceti's BERV and time are correlated at r = -0.93
  to -0.98, so a BERV slope can't be told from a drift through the season.
  A within-season time trend fits NEID at least as well (0.0096 +- 0.0019
  m/s per day, about 1.3 m/s over a season; NEID minus specfast 0.0073 +-
  0.0014). With both terms fitted, neither is cleanly separated. The likely
  sources are in NEID's CCF RVs (mask and template mismatch, telluric
  contamination that moves with BERV) or a slow instrument or calibration
  drift that specfast's template fit absorbs differently. A wrong proper
  motion or coordinate would give a secular trend, not one that resets each
  season.
- **Red orders with NEID's telluric model divided out** (584-787 nm):
  per-order scatter reaches the formal error (2.1 vs 2.1-2.4 m/s; NEID's
  per-order CCF RVs scatter 7-14 m/s there). This works on tau Ceti, not on
  the Sun, because the +-22 km/s BERV spread separates star from
  tellurics. A red-only RV still has a 1.07 m/s excess.
- **An era break inside one DRP version.** Orders at 487-524 nm step by
  +-4-5 m/s between 2023B and 2024B (same sign in 2024B and 2025B), with
  0.9-1.2 m/s within-night scatter and no BERV dependence, although the
  DRP version and master wavelength file are unchanged. Splitting segment
  offsets at 2024-03-01 brings per-block residuals from 1.87x to 1.39x
  formal. NEID eras, like KiwiSpec's, must be found in the data; the DRP
  version is not enough.

Not all red-order and DSST runs reached the 0.02 m/s tolerance in 6
sweeps (last changes 0.003-0.015 m/s).

## 2026-11-25: Why two implementations of the same model disagree (cross-start test, PR #10)

specfast (v5-equivalent: point sampling, linear iodine depth) and the
test bed (wavedist QD) fitted the same model to the same exposures differ
by ~1.1-1.5 m/s per exposure, partly common across telescopes. Test on 40
exposures (2017-2020, 2,431 traces), parameters mapped exactly between
the two parameterizations:

- **Not the optimisers.** Each code's own solution is its own chi2
  minimum (the other code's solution is worse by a median chi2 of 807 and
  959). Started from the other's solution, specfast returns to its own
  velocity within a median 0.002 m/s and the test bed within 0.06 m/s;
  the disagreement is unchanged (per trace 6.4 -> 6.3 m/s robust,
  per exposure 1.47 -> 1.55).
- **The test bed's optimiser adds a little noise.** Spread of converged
  velocity over starts at v +-50 m/s and wavelength +-0.1 px: test bed
  (scipy trf) median 0.067, 90th percentile 0.38 m/s; specfast
  (Gauss-Newton) 0.004 / 0.03 m/s. At most a few tenths of a m/s per
  exposure; fixable with tighter tolerances.
- **The models differ in how the iodine atlas is represented.** Switching
  specfast's conventions toward the test bed's one at a time (10
  exposures; per-trace / per-exposure robust sd of the difference):

  | specfast variant | per trace | per exposure |
  |---|---|---|
  | base | 5.31 | 2.41 |
  | kernel truncated at 4 sigma | 5.35 | 2.40 |
  | atlas interpolated in transmission, not optical depth | 3.48 | 2.75 |
  | model grid anchored per trace | 4.52 | 2.37 |
  | all three | 1.72 | 1.02 |

  The remaining 1.7 m/s per trace is probably the pixel window, which
  still differs on 27% of traces.

**Reading.** The NIST scan (0.23 km/s steps) resampled onto a 0.25 km/s
model grid is not converged: the interpolation choice (linear in T or in
tau) and the grid phase move a trace's velocity by 3-5 m/s and an
exposure's by ~1 m/s. Neither convention is "right"; a 0.0625 km/s grid
moves per-trace velocities by ~2 m/s in both codes. These per-exposure
differences are not the common nightly excess, though they are of
similar size: the fine grid leaves both codes' ML excess unchanged
(test bed 1.54 -> 1.54, specfast 1.84 -> 1.81 m/s). Practical
consequence: the atlas must be represented on its native samples (or
oversampled well beyond them) with a stated interpolation, and the
representation tested by grid phase and interpolation changes, not by
grid step alone.

## 2026-11-25: Static optical LSF vs per-exposure illumination kernel (testbed branch lsfillum)

Question (JDE): the LSF varies across each order; fix the optical part
and fit only the variable part (illumination, assumed constant across the
detector) per exposure. Does that remove the night-to-night excess?

**Verdict: no.** The per-exposure kernel makes nightly rms worse on
tau Cet and sigma Dra. The one clear gain is a static, per-era LSF map
built from the B stars (Be0, 1,136 B-star frames over 2016-2026, 50,153
trace fits): tau Cet nightly 4.92 -> 4.77 m/s, within-night 2.96 -> 2.78,
RV-level sqrt(chi2r) 1.62 -> 1.50, and the two-star era zero-point steps
fall from 9.6 / 11.7 to 1.7 / 2.7 m/s (part of the era steps is static
LSF-shape change). (These are on the wavedist QD baseline, not the v5
episode-corrected numbers.)

Two-star fit (tau Cet + sigma Dra zero-points); nightly / within-night /
sqrt(chi2r), m/s:

| Level | tau Cet | sigma Dra |
|---|---|---|
| base (wavedist QD) | 4.92 / 2.96 / 1.62 | 11.15 / 5.23 / 1.78 |
| A: Gaussian map + per-exposure width, h3 | 5.44 / 2.99 / 1.65 | 11.38 / 5.64 |
| B0: one static B-star map | 4.97 / 2.86 / 1.64 | 11.06 / 5.47 / 1.80 |
| B-pix: B0 + per-exposure kernel | 5.08 / 3.01 / 1.62 | 11.15 / 5.84 / 1.78 |
| C: kernel linear along/across orders | 5.16 / 2.95 / 1.61 | 11.35 / 5.98 |
| **Be0: per-era B-star maps, no kernel** | **4.77 / 2.78 / 1.50** | **10.95 / 5.42 / 1.80** |
| Be0 + kernel | 5.00 / 2.99 / 1.61 | 11.11 / 5.80 / 1.82 |
| Be0 + kernel + hierarchical prior | 4.66 / 2.83 / 1.52 | 11.00 / 5.40 / 1.78 |
| E: 3 B-star PCs per exposure | 6.72 / 3.00 / 1.76 | 11.50 / 5.72 / 1.87 |

Kernels are gated (exposure-tels with < 8 usable traces keep the static
map; ungated they run to their bounds and move RVs by up to 400 m/s).

- **Why a better LSF fit gives worse RVs.** Spectral chi2 falls at every
  step (median chi2_r 4.53 -> 4.29), but the kernel's RV moves (2.3 m/s
  per night) barely track the RV error (corr -0.16 nightly), and the
  B-star-basis kernel E moves RVs in a direction that correlates
  *positively* with the error (+0.32 nightly). The common-to-all-telescopes
  part of the fitted kernel tracks BERV and season (E's h3-like component:
  r = +0.42 with BERV, +0.40 with season). So on stellar frames the
  per-exposure "LSF" mostly absorbs a BERV- and season-dependent
  star-iodine mismatch (template), not the instrument. Real LSF changes
  are best captured as static per-era maps from the B stars.
- **h3 does not soak up velocity.** Injection on a real tau Cet frame: dh3
  +0.005 recovered as 0.00517 with a -0.27 m/s leak (vs +7.8 m/s with h3
  unfitted); a +5 m/s injection recovered as 4.70 with the kernel free and
  4.68 frozen. d<v>/dh3 = -16 m/s per 0.01, matching iodinfo.
- **The kernel is mostly constant across the detector** (JDE's assumption
  holds): along-order terms and the across-order h3 term are at noise. An
  across-order width term is real (sd 0.005-0.010 vs error 0.002) but
  RV-neutral.
- **Illumination vs thermal focus.** Per-exposure width follows throughput
  and seeing (FAU star size) more than temperature; only T3 is strongly
  covariate-driven (spectrograph pressure t = -5.9, iodine-cell
  temperature t = -3.4). Width-temperature slopes are significant per
  trace (57 of 92 cells, |t| > 3) but RV-neutral (map linear in bench
  temperature: 4.91 vs 4.94). B-star PCA: PC1 (76%) is a uniform width
  change common to all telescopes; PC2 (10%) is width varying across
  orders, red-heavy (the thermal-focus signature); PC3 (2.5%) is an h3/h4
  mix that differs by telescope. Velocity sensitivity per 1 sd of B-star
  variation: PC1 +0.25, PC2 +0.88, PC3 -1.68 m/s.
- **Known events seen in the kernel.** T2 at the 2018-12-17 break: dh3
  +0.009, width +0.019 (the per-era B-star maps independently show T2 h3
  going from +0.0004 to +0.0081, so a real LSF change). T2 feed deficit
  2018-10..12: dh3 -0.008. T1, T3, T4 show nothing at the T2 events.
- **HD 122064 is the exception.** Its 2016-20 data are dominated by T2
  feed problems, and the kernel genuinely corrects them: nightly 9.16 ->
  7.96 (within-night 6.49 -> 7.38); the kernel's RV change anticorrelates
  with the RV error (-0.44). 51 Peg: K stable (54.45 +- 1.53 -> 54.75 +-
  1.26), residual rms 3.64 -> 2.87.

**Decision for specfast:** the default LSF is a static per-era optical map
from the B stars (DESIGN.md "optics" frame). A per-exposure illumination
kernel stays available, off by default, under a hierarchical per
(telescope, era) prior, and only for exposures with enough traces; it
should be switched on where a feed problem is known (T2 2018). The
BERV/season mismatch it exposes belongs to the template (infer mode), not
the LSF.

Eras with no B-star frames fall back to the all-era map: e2016b, e2026,
and T4 in e2024. A consistent per-era run on the new extraction (x2) waits
for x2-0.4.

## 2026-11-25: NEID solar data through specfast (PR #9)

specfast reads NEID's public L1/L2 (converter and instrument description,
PR #9) and runs its template module with no iodine on the solar feed: six
clear days (40 x 55 s frames each), low activity 2021-04-03, 05-02, 05-29
(sunspot number 0-15) and high activity 2024-04-22, 05-17, 06-03 (SN
203-266). Infer mode, L1 wavelengths fixed, Gaussian LSF at R = 110k,
1024-px segments, 18 telluric-light orders (409-639 nm), one template per
NEID era.

| | 2021 (low activity) | 2024 (high activity) |
|---|---|---|
| rms(specfast - NEID DRP) per exposure | 0.33 m/s | 0.36 m/s |
| daily means: specfast / NEID / difference | 0.40 / 0.34 / 0.15 | 2.12 / 2.01 / 0.13 |
| within-day rms: specfast / NEID | 0.80 / 0.78 | 0.87 / 0.81 |
| formal error: specfast (18 orders) / NEID (77 orders) | 0.22 / 0.23 | 0.25 / 0.25 |
| residual / formal per segment | 1.13 | 1.12 |
| per-order scatter: specfast / NEID CCF | 0.7-1.7 / 1.8-3.7 | 0.8-1.8 / 2.2-4.5 |

- specfast matches NEID's pipeline to ~0.35 m/s per exposure and ~0.14
  m/s in daily means at equal formal error from a quarter of the orders;
  its clean orders are photon-limited (1.0-1.4x formal), NEID's per-order
  CCF scatter 2-3x. Modify mode (IAG solar atlas prior) agrees with infer
  mode to 0.02 m/s.
- **NEID needs era breaks too:** one template across 2021 and 2024
  inflates residuals to 2.8x formal; per-era templates (or per-(segment,
  era) offsets) fix it. Between the eras NEID's master wavelength solution
  changed and the instrument was recommissioned after the 2022 fire.
- **Red telluric orders are not photon-limited** (2-5x formal, drifting
  against NEID). The Sun's barycentric spread within a day (~0.14 km/s)
  can't separate template from tellurics (the separability check flags
  it), so solar tellurics need an external model.
- Template zero points against the IAG solar atlas are chromatic (+15..+25
  m/s at 600-750 nm, -15..-40 at 410-460 nm): the atlas's or NEID's
  absolute scale; open.
- Public solar data: 2021-01..2024-06 and 2025-02..2026-11, ~250 frames
  per day; L2 contains L1 plus tellurics, PWV, CCFs, activity indices, a
  chromatic exposure meter and per-order flux-weighted barycentric
  corrections. tau Ceti: 1188 public frames on 158 nights (not yet
  downloaded). L0 extraction scoped: it needs exactly G-CLEF's
  calibration path (per-fibre flats, 2D scattered light, fixed weights,
  comb-light subtraction, a comb pixel-position map).
- SDO/HMI activity references for the validation set were compiled from
  memory and still need verifying.

## 2026-11-25: Wavelength structure measured on B-star iodine frames (testbed branch bstarwave)

Test-bed branch `bstarwave` (private test-bed repo, afae175). 50,132
B-star traces from 892 frames (2016-2026); 2.61M independent 32-px
windows, each with a local shift fitted against the NIST atlas through the
per-era B-star LSF (no stellar template involved). Same-night pairs show the
formal window errors are ~1.18x too small.

| Model | chi2_r | Excess beyond noise (px / m/s) |
|---|---|---|
| Quadratic | 11.2 | 0.072 / 82 |
| Quadratic + D | 3.51 | 0.036 / 41 |
| Quartic + D | 2.69 | 0.029 / 34 |
| Sextic + D | 1.93 | 0.021 / 24 |
| Spline, 128-px knots + D | 1.83 | 0.017 / 20 |
| **Static table S (cross-fitted) + quadratic + D** | **1.62** | **0.018 / 21** |
| Static table + sextic + D | 1.55 | 0.016 / 19 |

- **JDE was right that the solution needs much more than a quadratic, but
  nearly all of it is static.** Same-night pairs (< 2.4 h) show nothing
  varying beyond noise; per-(tel, era) maps of ~0.04 px (48 m/s) have
  split-half r 0.87-0.98, are ~90% common to all telescopes (r 0.82-0.90),
  stable across eras (r 0.86-0.97), move with the spectrum across the
  remount (r 0.70-0.79 at the same wavelength vs 0.49-0.57 at the same
  pixel: optics or the iodine/LSF model, not the detector), and are
  identical for 8 different B stars (r 0.97-0.99). Largest in the red
  orders 19-23 and at order edges.
- **Per exposure:** higher-order terms are worth <= 1 m/s at exposure
  level; a small all-order degree 4-6 component (~0.01 px) correlates only
  with exposure time (untested, possibly count-level).
- **Cost in RV if left unmodelled:** 11-18 m/s rms per (tel, order) and
  21-35 m/s per quarter-segment, static, absorbed by the nuisance offsets;
  ~25 m/s of the 77-120 m/s static per-segment structure in star fits is
  wavelength, the rest template (as wavedist concluded). It predicts
  per-order BERV curves of ~4 m/s rms (stars cross it as BERV changes):
  weak match to bervcheck overall (r 0.16) but good in orders 8 and 19.
- **Stitching:** e2v CCD42-40-class, block layout unpublished. The pixel
  flat shows no stitch line crossing the dispersion (it can't see lines
  along the dispersion). Local step fits at 256/512/1024 multiples: no
  common detector step above ~0.01 px (signs flip across the remount;
  1536 is a marginal candidate). Predicted BERV errors from such steps
  0.6-1.0 m/s rms per order, uncorrelated with bervcheck. Stitching does
  not explain the BERV pattern.
- e2016c (Dec 2016-Apr 2017) B-star frames are unreliable (stale
  wavelengths); its map falls back to e2017.

Design consequence: wavelength = p + D(p) + S(tel, era, order, p) as
per-era calibration products from B stars, plus a per-exposure quadratic.
Product: kiwispec_wavestatic_v1.fits (radish results directory).

## 2026-11-24: Is the common nightly excess stellar? (testbed branch activity)

Test-bed branch `activity` (private test-bed repo, 5f054de). Chain =
episodes v5 (reproduced exactly).

**Literature (compiled by an agent; citations to be verified before use):**

| | tau Cet | sigma Dra | HD 122064 |
|---|---|---|---|
| Type, log R'HK | G8V, -4.96, flat, no cycle | K0V, -4.81, ~6 yr cycle (RV K ~2.0 m/s, correlated with S) | K3V, -4.83..-4.95, 12.8 yr cycle (RV K ~1.75 m/s at ~3100 d, attributed to activity) |
| Survey precision | HARPS ~0.9 m/s nightly; ESPRESSO ~0.7 | APF jitter ~0.6 m/s | HIRES floor 1-2 m/s |
| Expected stellar total at MINERVA cadence | ~0.7 m/s | 1.0-1.7 m/s | 0.8-1.2 m/s |
| Observed nightly excess | 1.75 | 2.66 | 3.13 |

So stellar activity is ~15% of tau Cet's excess variance and roughly half
of the other two (cycle terms dominate). tau Cet's 0.6-0.9 m/s red noise
matches the stellar prediction; the ~2 m/s red noise of sigma Dra and HD
122064 is ~2x it. p-modes are negligible for 15-30 min exposures.

**Diagnostics:**
- **Telescope-split test** (random halves of each exposure's telescopes;
  their covariance is noise-free): common nightly signal 1.79 / 2.72 /
  2.91 m/s, matching the ML excess. The excess is entirely common.
- **Chromatic RV:** a spot predicts ~-0.09 of the RV per 100 nm over
  500-620 nm, 6-15x below the per-night slope noise (5-8 m/s per 100 nm):
  chromatic RV cannot see activity in this band at this S/N. There is a
  common chromatic nightly term (3-5 m/s per 100 nm), but it does not track
  the RV excess (tau Cet kappa +0.4 +/- 1.2; sigma Dra -1.0 +/- 0.5, ~10x the
  spot prediction and look-elsewhere level).
- **Order structure:** a common, non-achromatic per-order nightly scatter of
  ~8-10 m/s per order (tau Cet), uncorrelated with the excess (|r| < 0.2),
  mostly cancelling in the exposure RV; partly the BERV pattern.
  Instrumental or template-related, not stellar.
- **Frame-separated shape terms** (instrument LSF width/skew vs star-only
  broadening/skew/line depth, by joint residual projection): all vary night
  to night far beyond noise, mostly in common across telescopes; none
  correlates with the excess (|z| <= 2.0).
- **Line groups** (depth, colour, from ~1000-2000 template lines) and **Na D
  / Mg b core indices:** null against the excess (one 2.7 sd hit, sigma Dra
  Na D1 on 49 nights, at look-elsewhere level).
- **Held-out checks** (train on alternate seasons): shape-term and
  chromatic regressions and activity-selected line masks give no
  consistent gain against random masks of equal weight.

Verdict: the common nightly excess is mostly not stellar for tau Cet
(and about half stellar for sigma Dra and HD 122064). It is achromatic and
common to all telescopes, which points at spectrograph- or analysis-side
terms shared by every fibre: the wavelength/LSF model, the iodine model,
the template, or a common instrument mode. Large instrument-common nightly
modes exist (chromatic slope, per-order scatter, LSF width, line depth)
and must be modelled as instrument terms before any stellar attribution.
Stellar mitigation is validated on NEID solar data first.

## 2026-11-24: T2/T3 episodes and the tau Cet budget (testbed branch episodes)

Test-bed branch `episodes` (private test-bed repo, 4a40185). Per-telescope
differentials (each telescope minus the weighted mean of the others in the
same exposure, timing-corrected), pooled over tau Cet, sigma Dra and HD
122064, segmented for mean and scatter changes (penalty from shuffled
series).

- **The chain was not applying kiwispec.yaml's per-telescope breaks or
  exclusions** (only branch telbreaks had them). Applied: tau Cet nightly
  4.30 -> 4.13 m/s, sigma Dra 11.25 -> 10.94, HD 122064 9.01 -> 8.59.
- **Episodes:**

  | Episode | Telescope, dates | Step / extra scatter | Cause | Remedy |
  |---|---|---|---|---|
  | E1 | T2, 2018-10-10..12-09 | -10.0 +/- 1.0 m/s, 4.2 m/s scatter (tracks guide offset, +11 m/s per arcsec) | T2 feed between the 2018-09 and 2018-12 trips (FAU star size 5.5" vs 1.5", throughput -1.1 dex, h3 -0.009) | the yaml 2018-12-17 break |
  | E2 | T2, at the 2018-12 trip | +1.7 | ZWO cameras and refocus | the yaml break |
  | E4 | T2 vs T1, 2025-12-10..2026-01-12 | -4.7 +/- 1.1 | T2 throughput down ~0.3 dex from 12-10; unidentified | a break (no gain on tau Cet) |
  | T2 count slope | T2 after 2018-12 | +3.8 m/s/dex | count-level, T2 only (not CTI) | regression, 0.33 m/s |

  T3 has no episode in any star. After the fixes every telescope's
  differential is consistent with its errors (chi2_r 0.92-1.02).
- **Why T2 and T3 looked 2x worse:** the per-telescope figure was an
  unweighted rms, and T2/T3 have more low-throughput nights (18% of T3
  nights have errors > 8 m/s). Their remaining rms matches formal errors
  plus the common excess to ~15%.

**tau Cet budget after timing, breaks and regressions (m/s):**

| | Nightly | Within-night |
|---|---|---|
| Observed rms (unweighted) | 4.12 | 2.56 |
| Weighted rms | 2.42 | |
| Formal (photon) error, median | 1.79 | 2.05 per exposure |
| ML excess beyond formal | **1.75 [1.58, 1.93]** | **0.00 (< 0.33)** |

- The unweighted nightly rms is mostly photon noise from a few faint
  nights: 7 nights above 10 m/s (3%) contribute ~2.9 m/s in quadrature.
- Formal errors are photon errors x 0.85 on every telescope; rms(z) 0.98
  on good nights.
- Quadrature contributions removed from the nightly excess: timing 1.83
  (ML; 2.39 on the unweighted rms), the per-telescope breaks 1.06, the T2
  count slope 0.33; exclusions ~0.
- **What remains: a nightly excess of ~1.75 m/s, the same on all four
  telescopes** (per-telescope part < 0.64 m/s at 95%). Within a night the
  data are photon-limited. sigma Dra and HD 122064 have ML nightly excess
  2.66 and 3.13 m/s (weighted rms 3.0, 3.5), within-night 0.
- Photon floor with four healthy telescopes at T1/T4 counts: 1.51 m/s per
  exposure, ~1.07 nightly at 2 exposures; with the 1.75 excess, ~2.05
  nightly. Today the median exposure has 3 telescopes; 16% have all four.

Verdict: tau Cet's error is photon noise within a night plus a ~1.75 m/s
night-to-night term common to all telescopes. That common term is the
limiting systematic; candidates are the star, the templates (the
BERV-dependent pattern is ~1.1 of it), the wavelength/LSF model and an
instrument common mode. Report weighted or ML nightly statistics, and make
the per-telescope breaks part of the standard chain.

### Follow-up: is the 1.75 m/s excess real, and does binning help? (2026-11-24)

- **Not a gain error.** The formal errors are fitted photon errors x 0.85
  (beta, the same on every telescope), and the within-night scatter matches
  them (excess 0.00, < 0.33 m/s). So the error scale is calibrated on the
  data. To absorb a 1.75 m/s nightly excess on 1.79 m/s formal errors they
  would have to be 1.4x larger, i.e. the gain wrong by ~2x; the PTC gain
  (1.265 e-/ADU) and the legacy value (1.30) agree to 3%.
- **Binning in time** (weighted bins of nights with formal error < 5 m/s,
  after all fixes; compared with simulated white noise of formal error +
  the fitted nightly excess, same sampling):

  | Bin (days) | tau Cet wrms | white | sigma Dra wrms | white | HD 122064 wrms | white |
  |---|---|---|---|---|---|---|
  | 1 | 2.31 | 2.21 | 2.83 | 2.85 | 3.24 | 3.40 |
  | 16 | 1.38 | 1.02 | 2.49 | 1.21 | 2.56 | 1.53 |
  | 64 | 1.11 | 0.73 | 2.24 | 0.73 | 2.21 | 0.97 |
  | 256 | 0.79 | 0.54 | 1.72 | 0.43 | 1.03 | 0.59 |

  tau Cet averages down to ~1 m/s on months and ~0.8 m/s per ~year bin,
  with a red component of ~0.6-0.9 m/s beyond white on 16-256 day scales.
  sigma Dra and HD 122064 carry ~2 m/s of red noise on weeks to months
  (stellar activity is a candidate: era zero-points already remove the
  common instrument mode at era level). Cross-star correlation of binned
  residuals is inconclusive (5-14 overlapping bins). Results:
  work/results/allan/ (radish).

## 2026-11-24: Charge-transfer inefficiency (testbed branch cti)

Test-bed branch `cti` (private test-bed repo, 5c2a42b).
- **Geometry:** dispersion runs along the serial register; the single
  amplifier is at the blue end of every order, so a pixel makes 51-2098
  serial transfers and deferred charge trails redward. Cross-dispersion
  is the parallel direction (shifts no wavelengths to first order).
- **CTE per era (serial EPER, 2016-2026):** charge lost per transfer
  ~4e-6 at 1k ADU, ~1.3e-6 at 10k (CTE 0.999995 / 0.9999987); deferred
  charge ~9 ADU x (S / 1000 ADU)^0.5 per row; trail 2.5e-4 S exp(-k/2.2) +
  1.5e-4 S exp(-k/18-24). No era trend beyond +/-30% and no CCD-temperature
  dependence over -85..-90 C. Parallel CTI not measurable.
- **Prediction (specfast forward model, trap model calibrated to EPER):**
  an apparent redshift falling with counts, +0.24..+0.29 m/s at tau Cet's
  ~1e4 ADU per column; slope -0.2 to -0.46 m/s/dex locally (worst case -0.7
  to -1.2), identical for all telescopes.
- **Observed:** the count slope is T2-only (tau Cet T2 +2.8 +/- 1.1,
  sigma Dra +5.6 +/- 1.0 m/s/dex; T1, T3, T4 consistent with zero), positive,
  and has no dependence on the number of transfers (by order or quarter
  along the order). The across-night exposure slope vanishes within nights
  (a time confound).
- **Trace-level correction:** tau Cet nightly 4.87 -> 4.92 m/s (slightly
  worse); quadrature contribution ~0.26 m/s nightly, ~0.12 within-night
  (sigma Dra 0.44, HD 122064 0.35 nightly).

Verdict: CTI is real and minor (< 0.3 m/s at MINERVA's counts); the T2
count slope is a T2-specific feed effect, not the detector. A per-pixel
CTI term belongs in specfast's detector frame for faint targets and for
G-CLEF, not in MINERVA's bright-star budget.

## 2026-11-24: Timing errors: photon-weighted midpoints (testbed branch timing)

Test-bed branch `timing` (private test-bed repo, commit 764360e). A
midpoint error dt gives an RV error (d v_bary/dt) dt; the rotation term
d v_bary/dt = v_rot w cos(HA) cos(dec) peaks at the meridian (it does not
change sign there; the velocity does). Median |rate|: tau Cet 2.8 cm/s
per s, sigma Dra 0.8, HD 122064 1.4. Correction applied: the full
flux-weighted average of v_bary over the exposure minus v_bary at the
header midpoint (DATE-OBS + EXPTIME/2).

Midpoint sources:
- **Exposure meter (2016-02..2020-09, all 873 exposures):** one
  photon-counting PMT on a pick-off in the collimated beam, i.e. all four
  fibres summed; 1 s gates time-tagged on the spectrograph PC (the same
  clock as DATE-OBS); not gated by the shutter. tau Cet ~1100 c/s against
  ~20 background. Flux-weighted minus geometric epoch: robust sigma / rms
  37 / 73 s (tau Cet), 53 / 167 (sigma Dra), 51 / 110 (HD 122064). In ~30%
  of tau Cet and sigma Dra exposures the summed rate is below half its
  median in the first 10 s (~20% at 250 s): acquisition and autofocus were
  still running ~30 s after DATE-OBS.
- **FAU photometry x guide-log coupling (per telescope):** guide gaps
  over 100 s in 22-43% of (exposure, telescope) pairs per year in
  2016-2020, 0-8% after.
- **Clocks:** spectrograph PC vs the NTP-synced gateway, from 7,624
  backlight events: +0.7 s (sd 0.3) normally; 42-61 s behind and
  free-running 2016-12-12..2017-01-12; 7.6 s behind on 2018-12-29 (43
  exposures, 0.1-1.4 m/s; corrected).

tau Cet, wavedist QD level 1 (baseline nightly / within / total 4.92 /
2.96 / 4.76 m/s):

| Source | Predicted -> observed slope (within / nightly) | Refit nightly / within / total |
|---|---|---|
| Exposure meter (summed) | 1.10 +/- 0.14 / 0.85 +/- 0.17 | 4.67 / 2.62 / 4.46 |
| Meter split per telescope by the guide model | 1.00 +/- 0.13 / 0.95 +/- 0.14 | 4.45 / 2.62 / 4.31 |
| FAU flux x guide coupling | 0.92 +/- 0.12 / 0.96 +/- 0.13 | 4.36 / 2.64 / 4.20 |
| Best (split meter 2016-20, else FAU model; + clock) | | **4.30 / 2.65 / 4.12** |

- No fitted parameter; slopes ~1. Shuffled nulls (500 each): within-night
  3.20-3.26 vs 2.62 observed; nightly 5.17-5.32 vs 4.43-4.69 (p < 0.002).
  Dropping the 20 largest corrections keeps the gain.
- The per-telescope differential part is detected (slope 1.03 +/- 0.26;
  T1 1.85, T2 1.11, T3 1.26, T4 ~0).
- tau Cet's within-night trend with hour angle (-0.15 +/- 0.06 m/s per
  hour) disappears (-0.01 +/- 0.06).
- sigma Dra and HD 122064: no significant change (rates 3-4x lower,
  predicted 0.6-1.5 m/s against 5-11 m/s of other scatter).
- **Quadrature contribution, tau Cet:** nightly 2.26 +/- 0.49 m/s,
  within-night 1.30 +/- 0.76 (2016-2020: 2.30 and 1.74). Post-2020 typical
  timing error ~0.6 m/s, apart from three lost-guiding exposures (6.5-7.8
  m/s). This is the earlier flux-midpoint gain (4.63 -> 4.00, 2.3 m/s in
  quadrature).

Verdict: timing is a measured term, about a third of tau Cet's nightly
variance, and the largest single one identified so far. For robofast:
per-telescope flux logging (guider flux and offsets on every frame, no
gaps while headers are collected), no shutter until every telescope is
acquired and guiding, a flux-weighted midpoint and flux-weighted v_bary
per telescope in the header (or the record itself, for the raw-redshift
release), NTP on every PC with an alarm above 0.5 s, shutter times from
the camera hardware.

### Follow-up: FAU flux as a fibre-coupling record, and confocality (timing, adbf6df)

- **Guide gaps were autofocus.** 788 FAU autofocus runs end inside
  2016-2020 RV exposures, a median 176 s after shutter open; the header
  DEFOCUS values (-1.5, -1.2, -0.8, +1.5 mm) are autofocus steps caught by
  the header read. This is the main cause of the timing term.
- **Sandberg's 2016 method** (aperture at XFIBER/YFIBER, flux-weighted
  v_bary over FAU frames; JDE's undergraduate project): as run (10 px
  radius = 3.3" in 2016-18) it works but trails our FAU source (tau Cet
  refit nightly 4.55 vs 4.36); with a fibre-sized aperture his signed
  weights fail (epochs far outside the exposure). Guider plate scale
  0.334"/px to 2018-12-15, 0.265 after; fibre radius 3.4 / 4.3 px.
- **Coupling profile fitted to the exposure meter** (2016-2020, tau Cet and
  sigma Dra, 491 exposures): the meter is best predicted by a narrow kernel
  centred within ~1" of the fibre position (Gaussian sigma 0.5" or the
  fibre disc, R^2 0.915 with offsets; total star flux 0.71; rings never
  win). Timing with it: tau Cet refit nightly 4.34, within 2.61 (baseline
  4.92 / 2.96), slope ~1, quadrature 2.21 +/- 0.49 nightly. No FAU source
  is "as good as the meter" (R^2 of epoch offsets 0.6-0.77).
- **Confocality.** Autofocus sweeps inside exposures (558 runs) put the
  fibre's best focus within ~100 um of the guider's (330 um at f/6.6 blurs
  by one fibre diameter) for T2, T3 and T4, stable across eras. **T1 looks
  defocused at the fibre by +600-900 um** in both camera eras, and its
  coupling-vs-seeing slope in 2016-18 prefers a blurred (~8") fibre image.
  T2 was badly defocused in 2018 (FAU half-flux size 10.7"; the E1
  episode).
- So a FAU-based per-telescope flux record is trustworthy for timing if it
  uses a small kernel on the fibre and every frame. For robofast: no
  autofocus during science exposures; log every FAU frame with a
  fibre-centred flux; re-measure each telescope's fibre-to-guider focus
  offset (T1 first).

### Follow-up: 2016 fibre rasters and the 2016-02-05 backlight series (timing, 11e0e2d)

- **Rasters found** (JDE with Samson Johnson, spring 2016): the 2016 guide
  loop logged "applying offset to fiber position (x,y)" each cycle, and on
  2016-03-10 (T1, T2), 03-11 (T3), 03-31, 04-01, 04-02 (T2, T4) and 04-27
  (T4) it stepped through grids. The exposure meter (not gated by the
  shutter) recorded the fibre-coupled light throughout.
- **Coupling maps** (meter / FAU flux against star-fibre offset, fitted
  with the 2.3" octagon convolved with the image the fibre sees):

  | Night, tel | Peak vs logged fibre (") | FAU core FWHM (") | Extra blur at the fibre (disc D, ") | Quality |
  |---|---|---|---|---|
  | 03-10 T1 | (+0.2, -0.5) | 4.1 | < 1.4 (confocal) | good |
  | 03-10 T2 (1-D) | (-0.1, +0.1) | 3.7 | 5.5-6 | good |
  | 04-02 T2 | (-1.1, +0.2) | 4.2 | 7.5 | clean map |
  | 04-02 T4 | (+2.8, +1.7) | 3.1 (saturated) | ~3 | fair |
  | 03-31 T4 | (+1.2..+2.9, +1.4..+2.7) | 3.9 | ~6 | degenerate |
  | 03-11 T3 | (-0.2, -0.2) | 4.6 | unconstrained | other tels dominate the meter |

  Scintillation gives chi2_r 3-30, so the errors are underestimated. FAU
  images in early 2016 were broad (3.7-4.6" core FWHM, vs ~3" from 2017).
  No spectra were taken while stepping, so there is no RV-vs-offset slope.
- **Backlight series 2016-02-05:** the index 73-92 is the I2 stage
  position (mm), not a focus scan. Backlit fibre spot at its brightest: T2
  near a sharp fibre image (half-flux radius 0.9"); T3 moderately blurred
  (1.4"); T1 blurred (1.8", ~2.2x ideal); T4 worst (2.1", with a halo).
- **Reading:** alignment changed after spring 2016. T2 and T4 were
  blurred at the fibre then but T2 is confocal in 2017-20 (autofocus
  test); T1 was confocal in March 2016 but is +600-900 um out in 2017-20.
  JDE: every FAU has been refocused since. T1's current state is on the
  site-visit list.

## 2026-11-24: Legacy production pipeline, tau Cet baseline

The legacy Doppler code's last tau Cet output (run 2019-04-29 on the
gateway; per-telescope RVs, 441 rows, 211 exposures, 2016-02-09 to
2019-01-28) was binned the way the test bed bins: per-telescope offsets
(weighted), exposure = weighted mean over telescopes, nightly = rms of
weighted nightly means. Median exposure error 3.0-3.2 m/s.

| Selection | Exposures / nights | Nightly rms | Within-night rms |
|---|---|---|---|
| all | 211 / 121 | 19.5 | 15.3 |
| error < 10 m/s | 193 / 116 | 11.5 (10.8 with per-era offsets) | 10.4 |
| error < 6 m/s | 177 / 107 | 8.2 (7.1 with per-era offsets) | 6.5 |
| error < 6, 2018-19 only | 89 / 62 | 5.3 | 4.0 |
| error < 10, by year: 2016 / 2017 / 2018 / 2019 | | 8.3 / 15.4 / 6.5 / 3.5 | 13.5 / 4.2 / 5.6 / 2.2 |

The test bed on the original extractions gives 4.6 m/s nightly over all
331 exposures (2016-2026), ~6.1 pre-2018 and 3.7-3.8 post-2018, so the
reimplementation is already 1.5-2x better than legacy over the legacy
span, mostly through the within-night scatter (legacy 6.5-10 m/s against
~3). The selections differ (legacy rows cut on its own errors; the test
bed on its gates), so this is a baseline, not a matched comparison; a
matched-exposure comparison is still to do. Files: legacy_rv results
directory (radish).

## 2026-11-24: Do residuals depend on barycentric velocity? (testbed branch bervcheck)

Test-bed branch `bervcheck` (private test-bed repo, commit 7a43294), on the
wavedist level-1 joint fits (quadratic wavelength; Q + D agrees to ~10%).
BERV rebuilt from the fitted velocity shift. Nulls: BERV shuffled within
season; BERV series rotated within season (keeps slow drifts, the honest
null); cross-season reproducibility of the BERV curve.

- **Per order, yes.** Residuals carry a BERV-dependent pattern of 4-7 m/s
  per order (4 km/s bins; sigma Dra 2.5), significant against the rotate
  null (tau Cet +9.8 sd, HD 122064 +6-7 sd), repeating from season to
  season (tau Cet r 0.58, HD 122064 0.42-0.46; sigma Dra 0.26, marginal,
  its BERV range is only +/-4.7 km/s and most of its signal is drift).
  Mostly non-linear in BERV; largest in orders 17-23 (11-15 m/s for tau
  Cet); common to all four telescopes.
- **Mostly not template-specific.** HD 122064 with rj08 vs rj122 on the
  same 12,396 traces: the per-order BERV curves correlate at r 0.98. The
  template-dependent part (rj08 - rj122) is ~1.6 m/s per order and ~0.75
  m/s rms in the exposure RV.
- **Small in the exposure RVs.** The per-order patterns largely cancel when
  orders combine. BERV terms explain 8 +/- 5% of tau Cet's night-to-night
  excess variance (~1.1 of 3.8 m/s; 95% upper limit ~1.7 m/s; not
  significant within a season), ~3% for sigma Dra, ~0 for HD 122064.
- **Confounders.** The pattern survives demeaning per (tel, order,
  season) and does not line up across stars in day of year (no annual
  instrument cycle); partial regression on airmass and temperature leaves
  the slopes unchanged. Tellurics were not tested.
- **Cause of the template-independent ~95% is open:** a detector-frame
  error (the template-module injection test shows exactly this signature:
  static pixel errors give BERV-repeating, telescope-common errors), the
  LSF or wavelength model acting on the stellar lines, tellurics, or an
  error shared by both DSSTs of the same star (both are deconvolved
  spectra of HD 122064). Pixel shift vs BERV across stars was
  inconclusive (only two stars overlap).

Verdict: most of tau Cet's 3.8 m/s night-to-night excess is not BERV
related. Inferred templates remain the right design (they remove the
40-100 m/s zero-points and serve stars without DSSTs) but will not by
themselves fix MINERVA's nightly scatter. Next checks on this pattern:
the per-order BERV curve against a model of tellurics and against the
detector-frame hypothesis once a pixel map exists (flats), and against
an inferred template (PR #7) on real data.

## 2026-11-24: Template inference module, injection tests (specfast PR #7)

Module `specfast.doppler.template`: per-order template on a fine ln(lambda)
grid (oversample 4), modes modify (prior + regularized correction, per-order
zero points as template properties) and infer (flat start); alternating
solver (block Gauss-Newton, banded sparse template solve, observatory
corrections, optional detector map); components for the star, iodine (with
learned correction), tellurics (dry x airmass, fitted water) and the
detector frame (pixel-edge offsets dx(p), response), the last kept separate
from the optics; an automatic separability check. Synthetic truth only.

- **MINERVA-like** (star + iodine, BERV +/-25 km/s, S/N ~140; slow run 4
  orders x 400 px x 24 exposures). Modify from a DSST-like prior with order
  zero points off by up to ~100 m/s and line depths 10% wrong: template
  error 0.0057 (prior 0.0157), zero points recovered to -4.9..+2.5 m/s,
  order offsets 34 -> 0.25 m/s, RVs unbiased (BERV slope -0.11 +/- 0.13
  m/s per km/s). Infer from flat: template error 0.0055, zero points +/-11
  m/s (relative RVs only), same RV scatter.
- **G-CLEF-like** (no iodine, comb-known wavelengths, noise-free,
  micro-tellurics < 1% deep): modelled tellurics leave 0.06-0.19 m/s;
  masking at T < 0.98 leaves 4.1-4.6 m/s, matching the predicted
  first-order bias (r 0.98-0.99). The size depends on the injected line
  list; the point is that masking is not a 10 cm/s option.
- **Detector frame**: dx of 5e-3 px rms plus a 0.02 px stitching step,
  ignored, gives 1.74 m/s RV errors that repeat at equal BERV (r 0.999)
  and bend the template; supplied as a calibration, they vanish. Fitting
  the map from the star data alone recovers it only partly (r 0.3-0.5;
  1.7 -> 1.3-1.6 m/s): the detector map must be a calibration product.
- **Degeneracy**: a BERV spread of +/-0.2 km/s is flagged (star vs
  observatory and star vs detector unseparable); +/-25 km/s is not.

Limits: the alternation converges slowly (~0.6 per sweep; ~0.5 m/s
changes persist after 6 sweeps noise-free), so the joint sparse solve is
needed for 10 cm/s; one velocity per (exposure, order), no per-segment
velocities or per-(telescope, order) offsets yet; diagonal template
sigma; no sky or charge-transfer terms; formal RV sigma slightly
conservative (rms/sigma 0.6-0.9). Not yet run on real data: needs a
driver from ExtractedSpectrum files and an on-disk template product.

## 2026-11-23: specfast skeleton and the injection test (PR #1)

- A self-consistent synthetic test (star with 3 km/s lines plus a dense
  iodine forest, K = 50 m/s, barycentric shifts to +/-30 km/s; v, iodine
  strength, cubic wavelength and quadratic continuum free) recovers K to
  -7e-8 noise-free, and -1.5e-5 when the truth is made on a 5x finer grid.
  Noisy pulls have std 0.99-1.00.
- **Pixel integration matters at the test bed's grid.** A piecewise-linear
  (trapezoid) pixel integral on a 0.25 km/s grid biases K by -0.3% and
  leaves ~0.1 m/s rms of barycentric-dependent error; the size scales with
  the stellar line width, not the iodine's. The integral of a cubic Hermite
  interpolant cuts it ~200x at the same cost; specfast uses it.
- So the test bed's 96.5% recovery is not a property of a self-consistent
  forward model: it is model mismatch (template, atlas or LSF), with at
  most ~0.3% from the pixel integration if the test bed integrates the
  same way (unchecked).

## 2026-11-23: KiwiSpec detector and order constants (specfast PR #2)

- **Echelle orders:** m = 122 - product index (0..28 -> 122..94); m*lambda
  is constant to 1e-5 across orders. A 31.6 l/mm R4 echelle. Pipeline
  wavelengths are vacuum. The arm covers 498.9-648.9 nm; RV orders 1-23
  cover 503.0-619.9 nm.
- **The unassigned trace (trace 0) is T4 of m = 123**, one order bluer than
  product order 0 (single-fibre flats, trace gaps and spectra agree). At
  the red edge, m = 94 keeps only T1 (T3 of index 28 is off the chip in
  every era). The test-bed extractor's `to_proc` is right; its docstring
  is wrong.
- **Detector:** 2052 x 2090 raw (42 serial overscan columns; skip the first
  6, trailing charge). Gain 1.265 +/- 0.02 e-/ADU (photon transfer,
  2016-2021). Read noise 2.85 ADU = 3.6 e-, stable 2016-2026 except
  2016-03-22..04-01 (6.1 e-); header RDNOISE = 3.63 is in electrons.
  Saturation plateau 62,300-63,030 ADU raw (use 62,000); linearity checked
  to 28k ADU only.
- **Consequences for x2:** SAT_ADU = 64000 never flagged saturation; the
  MAD read noise (3.145 ADU) is an integer-rounding artefact; 2016-03..06
  slit flats are saturated, so the pixel flats built from them are
  meaningless. Fixes sent to the x2-0.3 run, which had just started.
- **Odd periods:** a warm CCD (+23 C) on 2023-03-27..04-04, 2023-06-13..24
  and 2023-09-06..2024-03-13, with saturated science frames; other readout
  layouts (extra overclocked rows 2016-09-28..30, 2019-03-26,
  2023-03-23..04-04; 2096 x 2052 in 2022-01-28..03-16; no overscan in 2015
  and some 2023-04/05 frames); 1,761 frames in the camera's native format
  (exposure time in PARAM24 ms; all of 2016-09-15..27).
- **Header keywords:** TARGRAT/TARGDECT were used 2018-02-24..06-14;
  SPECPRES = -999 means missing; I2POSAS takes in/out/flat; robofast frames
  (2026-11 on) have no SPECPRES or target coordinates.

## 2026-11-23: G-CLEF from its optical design (specfast PR #3)

`specfast-zemax2instrument` (new `specfast.optics`: archive unpacking,
lens-file parser, sequential ray tracer, echellogram, YAML writer) traced
the 2021-12 G-CLEF design in full (no black boxes). On KiwiSpec, with
stand-ins for its black boxes, it agrees with the earlier private model to
2.4 um median along dispersion, with a constant 2.8 px cross-dispersion
offset from air/vacuum index handling.

- Blue arm: echelle orders 175-114, 347.3-541.6 nm; red arm: 114-64,
  534.4-967.2 nm; dichroic ~540 nm with order 114 on both arms. 10560^2 x
  9 um detectors. Red coverage ends at ~967 nm, not 1100 nm, with a 0.2 nm
  gap near 952 nm.
- Resolving power from the full 100 um core is ~73,000 (8.2 px); the public
  papers quote 108,000 at 7.5 px per resolution element, so the definitions
  differ. To pin down.
- Fibres 13.3 px apart along the slit (~7.8 px cores); orders 105 px apart
  at m = 175. Nine PRV fibres at that pitch span ~107 px, so in the blue
  (m ~175-165) the end traces of adjacent orders overlap or are closer than
  one pitch: extraction must model neighbouring orders' end traces, and a
  bright comb/etalon fibre at a slit end would sit on the next order's end
  science slice.
- The design's PRV slit has 7 science + 2 calibration/sky fibres, which
  conflicts with simultaneous comb + etalon + ThAr as three channels.

### G-CLEF modes and resolution (public sources, 2026-11-23)

- Ben-Ami et al. 2018 (SPIE 10702, 107029K), GMT modes: PRV R = 108,000,
  hexagonal 100 um core, 7 science + 2 calibration/sky fibres; NS-PRV the
  same with circular fibres; MR R = 35,000, 300 um; HT 450 um.
- G-CLEF@Magellan (EPRV5 poster, 2023-03): natural-seeing MR R = 100,000
  (1.12 arcsec, science + sky fibre) and HR R = 140,000 (0.8 arcsec,
  science + sky), plus a MagAO-X-fed pupil-sliced extreme-HR mode,
  R > 300,000 with 4 x 2 fibres. Calibration light goes in through a pair
  of calibration fibres into science/sky fibre pairs. So Magellan is not
  only "one slice": the MagAO-X mode slices into 4.
- The design's chief-ray trace gives R ~73,000 for the full width of a
  100 um core image (8.2 px); the quoted numbers are higher by factors that
  don't follow from one simple definition (a uniform disk's FWHM is 0.87
  of its width, giving ~85,000). The fibre sizes for the Magellan modes
  aren't public. Unresolved; specfast measures the LSF empirically
  (comb/etalon), so R in the config is informational only.

### G-CLEF observing modes in the instrument schema (2026-11-23)

The descriptions now list observing modes (JDE: "update the schema").
Tracing each GMT mode's fibre row through the 2021-12 design:

| GMT mode | Core | R quoted | R design (blue / red) | Quoted / design | Row offset along dispersion (blue) |
|---|---|---|---|---|---|
| PRV | 100 um hex | 108,000 | 73,400 / 73,000 | 1.47 | +14 px |
| NS-PRV | 100 um round | 108,000 | 73,300 / 72,900 | 1.47 | -15 px |
| MR | 300 um | 35,000 | 24,700 / 24,500 | 1.42 | +85 px |
| HT | 450 um | 19,000 | 16,300 / 16,200 | 1.17 | -53 px |

- The design's R x core is constant (~7.3e6 um), as it must be for a
  geometric definition. The quoted values are 1.17-1.47x higher, and not
  by a constant factor, so the papers' definition is not one simple
  rescaling (for the 100 um modes perhaps a slicer or sampling
  convention). Still to ask the instrument team.
- The Magellan fibre sizes follow from the poster: the f/11 beam is
  converted to f/3 at the fibre, i.e. 10.6 arcsec/mm on 6.5 m, so MR
  (1.12 arcsec) is ~106 um and HR (0.8 arcsec) ~76 um. With the quoted R,
  R x core = 10.6e6 for both, matching GMT PRV (10.8e6). So the Magellan
  MR/HR fibres are PRV-like and smaller, and the quoted R follow the
  papers' PRV convention.
- Correction to the subsection above: on Magellan the calibration light
  is injected at the front end into science/sky fibre pairs; there are no
  separate calibration fibres on the slit. The sky fibre of each pair
  therefore carries the simultaneous reference (comb, etalon or ThAr)
  when one is used. The poster also lists a MagAO-X single-fibre mode
  (0.8 arcsec, R 140,000) and a 16-spaxel MagAO-X IFU (R > 200,000); the
  4 x 2 pupil-sliced extreme-HR mode (1.05 arcsec, R > 300,000) is on the
  natural-seeing interface, not MagAO-X.
- The 2021-12 design models only the GMT fibre rows, so the Magellan modes
  carry no per-arm design values yet.
