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

### Held-out test (2026-11-26, testbed branch telbreak-holdout)

Asked: the overfit study found the frozen breaks help only tau Cet (-0.30).
Are they real or tuned to tau Cet? Frozen v5 set: T2 and T3 at
2018-12-17, T3 2024-11-20, T2 2025-12-10; exclusions T2 2019-05-08..07-14
and T3 2019-11-05..12-04. Full v5 chain (x2-0.4, timing from 2018, CTI,
floor 100, era zero-points) on 34 stars. Splits were fixed in advance.

- **The T2 2018-12-17 break (the site trip) is real.**
  - It is reselected in 7 of 8 half-splits (night or season, tau Cet
    alone or with sigma Dra and HD 122064). No other knob is chosen
    consistently.
  - Held out on tau Cet, alone: -0.23 [-0.47, +0.01], -0.45 [-0.76,
    -0.14], -0.59 [-0.83, -0.34], +0.00 [-0.11, +0.12] m/s ML excess
    (night A->B, B->A, season A->B, B->A).
  - It is far outside a null of 500 random-date draws: in-sample tau
    Cet gain -0.42 for the fixed set vs null 5-95% [-0.22, +0.01],
    P < 0.002.
  - **It improves stars never used to choose it**, paired, all data:
    HD 19373 -0.49 [-0.68, -0.29], HD 26965 -0.35 [-0.62, -0.13],
    HD 34411 -0.39 [-0.68, -0.07], HD 84737 -0.99 [-1.67, -0.57];
    sigma Dra -0.29 [-0.52, -0.08] in 2018-19. Over 16 other stars
    that span the break, 2018-19: 6 significant improvements, 1
    significant worsening (HD 62613 +0.12); median -0.06. Overall,
    HD 62613 +0.21 and 55 Cnc +0.48 get worse.
  - "Only tau Cet benefits" was sample size: HD 122064 has 4 nights of
    T2 after the trip.
  - Reservation: fitted on seasons B and scored on seasons A, the T2
    step gives nothing. The pre-trip T2 level was probably not constant
    (episode E1, 2018-10..12, sits inside it); untested.
- **The other knobs are not supported.**
  - T3 2018-12-17: about 0 in ML excess, slightly worse nightly rms.
  - T3 2024-11-20: no star has T3 data after it.
  - T2 2025-12-10: only tau Cet can test it; held out 0 to +0.14.
  - Both exclusions: about 0 on tau Cet. HD 190360 gets worse by +1.32
    [+0.88, +2.20] (19 of its 50 nights are in the T2 2019 window).
  - Recommendation: keep T2 2018-12-17; drop T3 2018-12-17, T2
    2025-12-10 and both exclusions unless an independent diagnostic
    supports them.
- **The original selection procedure could not tell real breaks from
  noise:** its 3-star nightly-rms objective is not unusual against the
  null (P = 0.21). Random exclusions alone cut sigma Dra's nightly rms by
  up to 1.9 m/s. ML excess discriminates; nightly rms does not.
- Caveats: HD 161797 (-3.7) and HD 95128 (-3.1) move in ML excess but
  not in weighted rms; do not use them as evidence. HD 93148 failed
  (ZeroDivisionError at level 1). The per-star era zero-point fit
  returns NaN for stars missing an adopted era; the holdout driver
  refits on the eras each star spans.
- Ledger: run ids `tbho_*`, `v5_x04_notelbrk` (baseline),
  `v5_x04_brkonly`, `v5_x04_tbh`. Test-3 rows hold the real gain in
  value and the null's 2.5-97.5% range in ci_lo/ci_hi.

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

## 2026-11-25: specfast joint model: the iodine gauge, 51 Peg, the port deficit, and iodine depth vs time (PR #10, 92c6a80)

**Gauge (`iodine.gauge: template`) changes nothing measurable on tau Cet:**
- Every metric is within ±0.02 m/s of the ungauged joint run (ML excess
  2.29 -> 2.29).
- Convergence still plateaus at about 1.35 m/s of offset change per
  sweep, so the drift is not along the iodine-correction/template
  direction.
- Untested guess: per-order zero points vs template shift under the
  modify-mode prior.

**The learned iodine correction is essential.** Switching it off (warm
start) raises tau Cet's ML excess to 14.2 m/s (+11.9 [10.1, 12.9]) and
chi2 by 18%. The atlas's optical-depth errors (~0.02) then go into the
modify-mode template as ~10 m/s errors that follow BERV.

**51 Peg (17 frames, 2017, 9.3 km/s BERV range):**

| Run | K (m/s) | rms (m/s) | BERV slope (m/s per km/s) |
|---|---|---|---|
| test-bed copy (v5eq) | 56.1 ± 1.3 | 3.4 | +0.3 |
| joint, own iodine correction | 57.3 ± 3.6 | 10.0 | +3.2 |
| joint, correction off | 58.1 ± 7.3 | 18.0 | +5.8 |
| joint, fixed template | 57.2 ± 1.9 | 5.1 | 0.0 |
| joint, modify template + tau Cet's correction frozen | 56.4 ± 1.5 | 4.6 | +0.2 |

- Carrying the correction over from a star with wide BERV coverage
  removes the BERV trend.
- This supports one observatory-frame correction shared by all targets
  (DESIGN, 03af581). A multi-star fit (M1) is next: 4 standards plus
  3 B stars, ~750 frames.

**Port deficit confirmed.** specfast's copy of the chain (v5eq) vs the
test bed's own x2-0.4 fits, identical exposures:
- ML excess +0.36 [0.14, 0.56] m/s, and +0.70 [0.31, 1.35] in 2020+.
- wrms +0.29 [0.15, 0.42].
- The same without timing (+0.34).

Where it comes from:
- specfast drops more traces (1968 test-bed-only vs 412 specfast-only),
  not because of the count floor.
- The per-(exposure, telescope) difference in 2020+ is 0.6 m/s for T1,
  T2 and T4 but **2.35 m/s for T3**.
- Per-order mean offsets reach ±12-16 m/s in 2020+ (orders 9, 10, 12).
- Next: atlas interpolation and grid phase on 2020+ T3.

**Water column vs residuals:** r = -0.27 [-0.38, -0.18] over all eras
(2016 -0.57, 2018-19 -0.37, 2020+ -0.05), about 0 within nights. This
may be seasonal confounding (water vs BERV season); it is not shown to
be a cause.

**Iodine depth falls with the cell temperature since 2020 (tau Cet).**
The per-exposure iodine scale k, normalised by its (telescope, order)
median, by period:

| 2016 | 2017 | 2018-19 | 2020 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|
| 1.03 | 1.00 | 1.04 | 0.97 | 0.94 | 0.925 | 0.92 |

- **The cell temperature is a real reading, recorded in 0.1 C steps.**
  The setpoint is always 55.0. The reading is 55.0 ± 0.1 C through
  2022, so the cell held its setpoint until then.
  - In 2024 it reads 54.8-54.9, in 2025 54.6-54.9 (mostly 54.7-54.8),
    and in 2026 54.6-54.8.
  - The cell has drifted 0.2-0.4 C below its setpoint since sometime
    in 2023-24. There are almost no tau Cet frames in 2021-23.
- Within 2020+, k tracks the temperature (r 0.85, 0.17 per K).
- The temperature does not explain all of the decline. 2020 is
  slightly warm (55.1) but already has k 0.97, compared with 1.04 in
  2018-19 at 55.0. So there is probably a slow decline in addition to
  the temperature effect.
- **The independent iodine-cell PT100 does not measure the cell
  itself.** It read 27-31 C, so it sat on the housing or mount, not at
  the cell's 55 C. It is cell-related only until it lost contact in
  2023-06.
  - Yearly means: 2016-18 27.5-28.0, 2019 28.5, 2020 30.4, 2021 29.7,
    2022 26.8.
  - The warm housing in 2020 coincides with the cell reading 55.1. The
    later cold period coincides with the cell reading below its
    setpoint (the room/bench probe is ~23 C in 2024-26).
  - Suggestion (not tested): the cell's control loop does not fully
    reject ambient temperature, so the cell follows the room by
    roughly 0.1-0.4 C.
- The absolute median k is 0.934: the NIST atlas is 5-7% too deep.
- k could also absorb LSF-width changes; the B-star test in the M1
  follow-up below rules that out.
- Earlier: the cell temperature does not correlate with the nightly RV
  residuals, so the fitted k absorbs the depth change.

### Follow-up: one iodine correction shared by all targets (M1; PR #10, 1ac0f54)

The joint model now takes a list of targets. The learned iodine
correction is solved once per order from every target's normal
equations, and each target keeps its own template and zero points.

**Synthetic test:** two stars with different BERV, plus a featureless
star, observed through a wrong iodine atlas. The learned correction
recovers the injected error (r 0.885) and the RVs are photon-limited.

**M1 data:** 428 frames from 2017 on, chi2r-weighted:
- tau Cet, sigma Dra and HD 122064 (up to 150 each);
- 51 Peg (17);
- 6 B stars (25 each, featureless).

2016 is excluded because sigma Dra's 2016-02 frames fit at chi2r 24.

Results:
- **Who constrains the shared correction.** Information shares: B
  stars 0.39, tau Cet 0.35, sigma Dra 0.22, HD 122064 0.03, 51 Peg
  0.01. The multi-star correction agrees with the tau-Cet-only one at
  median r 0.78 over orders (red orders 21-23 ~0.37).
- **51 Peg's BERV trend is gone with its own adjusted template:**
  slope -0.02 m/s per km/s, K 56.1 ± 1.7, rms 4.7. Learned on 51 Peg
  alone it was +3.2 and 57.3 ± 3.6.
- **The gauge is unnecessary with several targets:** gauge on vs off
  gives r 0.999 between corrections and a tau Cet excess change of
  -0.01.
- **tau Cet's excess does not move:** 2.40 -> 2.34, d -0.06 [-0.34,
  +0.25], 97 exposures, 2017+. The shared correction fixes
  short-baseline stars, not the ~1.4 m/s per-exposure term. The
  convergence plateau (offset increments of a few m/s per sweep) also
  remains.

**The iodine-depth drop since 2024 is the cell.** All B-star frames
from 2022 on, with the correction fixed and the depth k free per
exposure:

| Year | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| B stars | 1.006 | 1.017 | 0.949 | 0.921 | 0.912 |
| tau Cet | 0.996 | - | 0.931 | 0.921 | 0.916 |

- The B stars have no stellar lines, yet they show the same 8-9% drop.
- Within 2020+, k follows the cell temperature: B stars r 0.88,
  0.22 per K; tau Cet r 0.84, 0.21 per K.
- An LSF-width change would not follow the cell temperature within an
  era. The cause is the cell running ~0.3 C cold.
- In 2017-23 k is flat at 0.98-1.02 for every star.

**The 2020+ T3 port deficit is the iodine grid.** specfast's copy of
the chain vs the test bed on 2020+ T3 (32 exposures):

| Variant | per-exposure difference, robust sd (m/s) |
|---|---|
| base | 2.11 |
| atlas interpolated in transmission | 1.34 |
| grid shifted by half a step | 1.12 |
| both | 0.93 |

- The worst orders fall from 17-22 to 4-6 m/s.
- A half-step shift of the 0.25 km/s grid moving per-exposure
  velocities by 1-2 m/s means **the grid undersamples the iodine.**
  This violates DESIGN's < 0.1 m/s per exposure convergence
  requirement. specfast needs a finer grid, or a sampling-invariant
  atlas representation, before the port comparison means anything.

**Fix: average the iodine over each grid cell (PR #10, 322e50a).**
- Cause: the NIST atlas was point-sampled at the grid nodes, and its
  lines are narrower than 0.25 km/s.
  - A half-step phase changes the iodine factor by up to 5% and a
    block's velocity by 10-15 m/s.
  - Point sampling at 0.0625 km/s still leaves ~0.9 m/s per block.
    That is why grid refinement alone had appeared converged.
- `iodine.supersample: n` averages the transmission over n sub-samples
  per cell.
- Grid-phase test (phase 0 vs 0.5) on tau Cet 2018+, 393
  exposure-telescopes. Robust sd of the per-(exposure, telescope)
  difference:

| Setting | per exposure-telescope (m/s) | per block (m/s) |
|---|---|---|
| 0.25 km/s, point-sampled (old default) | 2.05 | 4.3 |
| 0.25 km/s, supersample 4 | 0.14 | 0.72 |
| 0.125 km/s, supersample 4 (adopted) | **0.068** | 0.27 |

  The adopted setting meets the < 0.1 m/s requirement at ~2x the CPU.
- **The shared correction saturates at a few hundred frames.** Using
  the 219 highest-S/N frames instead of M1's 428 gives the same
  correction (r 0.999, difference 5% of its rms). Fewer frames do cost
  the per-star templates: tau Cet's excess +0.28 [+0.12, +0.43], and
  51 Peg K 60.7 with BERV slope +1.1. More data is for the templates,
  not the shared term.
- **The port deficit closes over all eras** with the adopted setting.
  specfast's copy of the chain, paired on identical exposures:
  - vs its old point-sampled self: ML excess -0.30 [-0.52, -0.11],
    wrms -0.20 [-0.32, -0.08]. The aliasing was costing real precision.
  - vs the test bed: ML excess +0.04 [-0.22, +0.29] (was +0.35); tau
    Cet's ML excess is 1.75 m/s, the same as the test bed's.
  - **Still worse in 2020+:** +0.65 [+0.24, +1.39], wrms +0.36. The T3
    outlier is gone (per-exposure difference 1.0 m/s, like T1/T2).
  - **Explained: 2020+, paired vs the test bed** (118 exposures, 58
    nights):

    | Switch | ML excess d | wrms d |
    |---|---|---|
    | base (interpolation in optical depth) | +0.65 [+0.24, +1.39] | +0.36 |
    | + common traces only | +0.55 | +0.32 |
    | + interpolation in transmission | +0.37 [+0.04, +0.90] | +0.06 |
    | + both | **+0.07 [-0.18, +0.41]** | +0.03 |

    - Calibration inputs were already identical.
    - Interpolating the atlas linearly in optical depth vs in
      transmission halves the per-trace difference (4.8 -> 2.5 m/s).
      It accounts for most of the wrms and about half of the excess.
    - The trace gates account for the rest. Restricting the test bed
      to the common traces raises its own 2020+ excess, 1.39 -> 1.66.
  - **Why the interpolation choice matters:** the NIST atlas is
    sampled every 0.227 km/s, about the width of a line core. So
    linear interpolation in optical depth and in transmission differ
    at the percent level in the cores, at any model grid. Neither is
    exact: the atlas is under-resolved for linear interpolation.
  - **Linear in transmission is the right choice (c7d2bef, all 371 tau
    Cet frames, phase-invariant grid).**

    | Interpolation | chi2/ndata | median chi2r | median iodine k |
    |---|---|---|---|
    | linear in optical depth | 6.587 | 4.632 | 0.935 |
    | linear in transmission | 6.381 | 4.474 | 1.001 |
    | cubic spline in optical depth | 13.207 | 7.234 | 0.956 |

    - The cubic spline sharpens the line cores and doubles chi2. The
      NIST samples behave like bin averages, not point samples of a
      band-limited function, so a band-limited interpolant through them
      is the wrong reconstruction. Linear in transmission is close to
      preserving the bin averages.
    - With transmission, k is 1.00: the "NIST is 5-7% too deep" seen
      with optical-depth interpolation was partly that interpolation.
    - Paired tau Cet, timing from 2018:

      | Comparison | ML excess d | wrms d |
      |---|---|---|
      | optical depth -> transmission, all (326 exp, 195 nights) | -0.13 [-0.29, +0.07] | -0.14 [-0.24, -0.03] |
      | optical depth -> transmission, 2020+ | -0.49 [-0.96, -0.22] | -0.30 [-0.44, -0.16] |
      | transmission -> cubic, all | +3.50 [+2.78, +4.26] | |
      | test bed v5 -> specfast v5eq (transmission), all | **-0.09 [-0.21, +0.04]** | -0.06 [-0.13, +0.02] |
      | same, 2020+ | +0.16 [-0.09, +0.61] | |

    - **The v5eq port is closed:** specfast matches or slightly beats
      the test bed in every era. Its tau Cet ML excess is 1.62 m/s.
    - **The interpolation choice alone moves RVs by 0.71 m/s per
      (exposure, telescope), and 0.76 m/s in the part common to all
      telescopes** (258 exposures). An iodine-model error is shared by
      every telescope, so this is a candidate contributor to the
      unexplained common per-exposure term. Whether the learned
      correction (M1) absorbs it is running.
- **The multi-star joint model is unchanged by the grid fix**
  (tau Cet 0.00 [-0.05, +0.05]).
  - The aliasing is a static observed-frame error, and the learned
    iodine correction and depth absorb it: the correction moves (r
    0.969 vs before) while the RVs do not.
  - The v5-equivalent chain has no learned correction, so the error
    leaks into its velocities through each exposure's wavelength shift.
  - On the 97-exposure subset, the joint model still does not beat the
    v5-equivalent chain: +0.57 [-0.28, +1.62] m/s.
  - 51 Peg: K 56.0 ± 1.6, BERV slope +0.12.
- **The multi-star joint model with transmission interpolation**
  (`sf_m1_g0125ss4_tinterp`, 5 sweeps, still not converged: dv_p95 2.2):
  - tau Cet vs M1 at the grid fix: -0.07 [-0.18, +0.04]. vs v5eq with
    transmission (97 exposures): +0.64 [-0.20, +1.62]. The joint model
    still does not beat v5eq.
  - **The learned correction absorbs about half of the interpolation
    sensitivity for tau Cet:** per (exposure, telescope) and
    telescope-common robust sd 0.34 / 0.34 m/s (v5eq: 0.71 / 0.76). The
    correction itself moves by 0.009 rms, about 40% of its size. Absorption
    is weaker for sigma Dra (1.25 / 1.49) and 51 Peg (1.22).
  - So an iodine-model error of this kind is not removed by learning the
    correction; at most half of it is. The model of the iodine must be
    right in the first place, not learned around.
- **Water column** correlates with the joint model's level-1 residual (r
  -0.27 [-0.38, -0.18]) and with joint minus v5eq (-0.24). It may be
  seasonal; not yet separated from season.
- **Not done:** single-component ablations of the joint model (LSF,
  wavelength, telluric, CTI, BERV function, illumination kernel, infer
  mode). The convergence plateau (per-order zero-point increments of
  1.3-4.6 m/s per sweep in every joint and M1 run) is unresolved; a
  trade between the per-order zero point and a template shift is the
  working guess, untested.
- **The test bed's sampling (testbed branch i2super, 72386b6): the
  representation error is real but is not the 1.4 m/s term.**
  - Half-step grid-phase shift, tau Cet, 868 exposure-telescopes, robust
    sd per exposure-telescope / telescope-common, m/s:

    | Setting | per exp-tel | telescope-common |
    |---|---|---|
    | 0.25 km/s point-sampled (production) | 0.94 | 0.57 |
    | 0.25, iodine cell-averaged x4 | 0.33 | 0.23 |
    | 0.125, iodine cell-averaged x4 (specfast's setting) | 0.14 | 0.11 |
    | 0.25, iodine and stellar template cell-averaged x4, cubic pixel resampling | **0.03** | **0.03** |

  - The leftover after the iodine fix is the stellar template: DSST's
    native step (0.33 km/s) is coarser than the grid, so point-sampling it
    is phase-sensitive too. Cell-averaging both meets the < 0.1 m/s
    requirement at 0.25 km/s, at 2.5-3.5x the CPU.
  - **The converged model leaves the excess unchanged.** Full frozen v5
    chain (timing from 2018, CTI, breaks, T2 count slope, 100 e- floor),
    all three stars refit, paired: tau Cet 1.80 -> 1.80, +0.00 [-0.07,
    +0.07] m/s, and no era moves significantly (2020+ +0.11 [-0.05,
    +0.43]). sigma Dra all -0.03 [-0.06, +0.00]; 2016 **-0.18 [-0.23,
    -0.11]**. HD 122064 +0.00 [-0.06, +0.06].
  - The ~0.4 m/s rms per-exposure representation error mostly averages
    out within nights or is absorbed by the zero-points. The 1.4 m/s
    common term comes from outside the model-grid representation.
  - Point sampling at 0.0625 km/s is already close to converged in the
    test bed (0.11 / 0.07 m/s from the converged setting), which explains
    the earlier unchanged excess at 0.0625.
  - The half-step phase alone moves the excess by up to 0.1 m/s at the
    old setting, so single-run differences below ~0.1 are not significant
    there.
  - Ledger: baseline `v5_x04_cti_t18f100` (not the overfit `v5_x04_cti`,
    which has timing everywhere and no floor); `v5_x04_cti_i2ss4cs`
    (converged), `v5_x04_cti_i2ss4`, `v5_x04_cti_i2ss4g125`,
    `v5_x04_cti_g0625pt`.

## 2026-11-27: All stars, Charlie's chain as left vs frozen v5 (testbed branch allstars, 1b208d5)

Form A is Charlie's code as he left it (pristine checkout, paths only).
Form B is the frozen v5 chain: timing from 2018, CTI, floor 100, frozen
breaks, era zero-points. Both run on x2-0.4. The timing term exists only
for tau Cet, sigma Dra and HD 122064 (no FAU or exposure-meter curves for
the others). 135 targets have frames; scored A on 55 stars, B on 44; 47
targets Charlie never registered were added (configuration only).
Unusable, excluded: HD 16160 (80-110 m/s, cause unknown), HD 219834
(binary?), Procyon (solar atlas), HD 97601, eta Cas A, HD 9407, HD 93148
and the TOIs, HD 161797 and HD 95128 (excess moves without wrms).

- **ML nightly excess, A -> B, all eras:** tau Cet 2.51 -> **1.80
  [1.4, 2.2]**; sigma Dra 7.22 -> 3.00; HD 122064 5.00 -> 3.62; iota Per
  4.45 -> 2.85; HD 62613 4.72 -> 3.30; o2 Eri 4.86 -> 4.19; rho CrB 6.48 ->
  4.52; HD 127334 2.22 -> 2.02; HD 84737 1.59 -> 1.36. Quiet stars without
  timing (HD 48682, HD 34411, HD 55575) are unchanged at 2.6-2.8.
- **Paired chain effect (B - A, x04):** tau Cet -0.71 [-1.26, -0.15]
  (2018-19 -1.14); sigma Dra -4.26; HD 122064 -1.41. Most of the gain is
  in 2018-19. **B is worse than A in 2017** for tau Cet (0.27 -> 1.85) and
  HD 62613 (+1.90), and for HD 62613 also in 2018-19 and 2020+.
- **Paired extraction effect (x04 - original):** tau Cet none (A -0.01, B
  -0.06). sigma Dra B +0.37, all in 2016 (+0.86); HD 122064 B +0.94 (2016
  +1.21). **Charlie's unmodified code shows the same 2016 shift** (sigma
  Dra +0.89 [+0.17, +1.48]), so the 2016 deficit is the extraction, not
  our corrections. HD 62613 is better on x04 (-0.37).
- **Planet K recovered** (B / A vs literature): 51 Peg b 55.3 / 55.7
  (55.9); 55 Cnc b 71.8 / 71.4 (71.4), e 6.3 / 6.8 (6.0), f 5.2 / 2.9
  (5.1); rho CrB b 67.8 / 64.5 (67.4); HD 217107 b 139.7 / 139.6 (140).
  Periods longer than 1.5x the span are fitted as a quadratic trend.
- **A nightly term shared between stars exists, but it is not most of
  tau Cet's excess.** Random-night-effect model over 44 stars, form B,
  shuffled-night null: all-telescope shared term 0.84 [0.50, 1.10] m/s
  (null 95th percentile 0.61); same-telescope 1.14 [1.0, 1.3]. It
  survives a 30-day running-mean removal (0.81). By era: 2016 2.3
  (provisional), 2017 below 0.8, 2018-19 0.7-1.0. tau Cet's nightly
  residual vs the mean of other stars that night: covariance +0.15
  (null [-0.76, +0.71]), +0.46 detrended, so at most ~0.7 m/s of tau
  Cet's excess is shared with other stars; the rest is per star or per
  pointing. The shared term correlates weakly with enclosure humidity
  (r -0.14 / -0.18, p < 0.002; about 80 covariates tested, only this
  survives); not with iodine-cell, bench, CCD temperature or pressure.
  This supersedes the thermal study's "no shared term".
- Ledger: `as_charlie_x04`, `as_charlie_orig`, `as_v5_x04`, `as_v5_orig`
  (renamed from the agent's ids to avoid clashing with the overfit runs).
  Flagged stars carry "FLAGGED unusable" in notes.

## 2026-11-27: Independent review (read-only, a second model)

A reviewer read FINDINGS, DESIGN, the ledger and the code review and
spot-checked numbers in the result files. Its new results are not yet
reproduced by us; they set the next experiments.

- **tau Cet's excess is coherent over days, not random night to
  night.** Nightly-residual covariance vs lag (excess variance 3.14
  m/s^2): <= 1.5 d +3.36 +/- 0.62; 1.5-4.5 d +1.72 +/- 0.37; 4.5-15 d
  +0.04 +/- 0.20. The noise-only simulation gives +0.18 at the shortest
  lag. At short lag the covariance is positive only for |dBERV| < 1.5
  km/s. The full e2esim shows the same lag structure (its error is a
  function of BERV) but repeats across years at equal BERV far more than
  the data do (same-BERV cross-season covariance +3.4 simulated vs +0.66
  real). The "already full at a 1-day lag" statement in the diagnosis
  section predates v5 and is stale.
- **The excess falls by era:** 2017 2.2, 2018-19 1.74, 2020+ 1.31 m/s.
  The "1.4 m/s unexplained" is an era average and uses a simulation whose
  template mismatch is known to be inflated; for 2020+ about 0.9 is left.
- **A 2016 drift is shared by sigma Dra and HD 122064** (-2.5 to -4.9 m/s
  in 2016-05..06, at the enclosure set-point step). The thermal study's
  +/-15-day running median removed it. tau Cet vs sigma Dra stays null.
- **The formal errors overstate within-night scatter by ~20%**
  (within-night chi2r 0.65), so "within-night excess 0" is censored; the
  excess runs 2.00 -> 1.48 as the error scale goes x0.85 -> x1.18.
- **Weaker than stated:** "tellurics ruled out" (a linear test against a
  noisy proxy; the 0.995 mask lowered common excess 2.61 -> 2.21 at L0 and
  was never rerun under v5; a crude dry/wet split of the spectral water
  column gives 1.32 vs 2.07, unverified); the night-block bootstrap
  assumes independent nights, so CIs are too narrow given multi-day
  coherence (use blocks of a week or more); several pre-protocol
  conclusions were scored on nightly rms; the photon floor is quoted
  three ways.
- **Missing control:** the per-order common nightly scatter of 8-10 m/s
  divided by sqrt(23) is 1.7-2.1 m/s, the size of the excess. Untested:
  whether the excess is just the average of order-specific errors.
- **Ranked next experiments:** (1) order-split covariance (interleaved
  halves, blue vs red); (2) lag and BERV covariance on all stars: does the
  coherence time scale as 1/(dBERV/dt)?; (3) paired v5 rerun with
  stricter telluric masks (0.995, clean-model mask, orders 18-20 dropped),
  scored on ML excess and lag-1 covariance, plus calibrated PWV; (4)
  simulation variants that reproduce strong short-lag and weak
  annual-repeat covariance; (5) the same simulation for sigma Dra; (6) a
  2016-04 zero-point for sigma Dra and HD 122064.
- Recommended stopping: 2016 extraction forensics, more per-exposure LSF
  kernels, per-telescope break tuning, atlas work, G-CLEF extraction-mode
  simulations; fix the joint model's convergence before adding physics.
- **PI answers (2026-11-27):** there is no ADC. Atmospheric pressure may
  be in the FITS headers and is in the nightly logs; spectrograph pressure
  is in both. Spectrograph focus was never intentionally changed. Hour
  angle and B-star cadence are to be read from the data. External RVs for
  2017-19 probably exist (archive search running). An on-sky alternating
  two-standard test is approved in principle, about a month from
  resuming observing. Calibrated CAMAL PWV is not readily available; the
  route is to rerun the CAMAL team's public reduction code on the archived
  raw images (running).

## 2026-11-27: Structure of the excess: order split, lag vs BERV, stricter masks (testbed branch structure, eae31db)

The structure rerun of the frozen v5 chain reproduces the allstars tau
Cet series exactly (1.80; maximum difference 0 m/s on 352 exposures).

- **tau Cet's excess is mostly order-specific.** Nightly residuals from
  two order halves (odd/even; blue = orders 1-9 vs red = 10-23, equal
  information) share only 0.37 [-0.26, 0.80] and 0.21 [-0.53, 0.72] of
  the full excess variance. Each half's excess is 1.86-2.90 m/s, as
  expected for independent order errors (sqrt(2) x 1.80 = 2.55).
- **The other stars' excess is mostly common to all orders:** sigma Dra
  0.94 [0.69, 1.21] (odd/even) and 0.87 (blue/red); HD 122064 0.65-0.79;
  quiet stars HD 127334, HD 55575 0.65-1.06. So their excess is an
  achromatic shift of unknown origin (star, timing or instrument), unlike
  tau Cet's. HD 84737's covariance is 3x its excess squared: its formal
  errors are overstated, so ML excess understates it.
- **The coherence follows BERV, not elapsed time** (22 stars, each
  normalised by its excess variance, 30-day-block CIs, within-star
  permutation null):
  - lag <= 1.5 d +0.70 [0.49, 0.84]; 1.5-4.5 d +0.55; 4.5-15 d +0.22;
    > 45 d -0.07.
  - At 4.5-15 d lag: |dBERV| < 0.7 km/s +0.67 [0.24, 0.89], 0.7-1.5
    +0.34, 1.5-3 +0.07. At <= 4.5 d lag: +0.69 / +0.47 / +0.19 for the
    same |dBERV| bins.
  - Same BERV, lag > 200 d: +0.28 [-0.04, 0.50]; different BERV (> 3
    km/s): -0.12. Repeat across seasons is weak.
  - Coherence time: tau Cet 2.2 d (BERV rate 0.32 km/s/d), sigma Dra 34
    d (0.07; 17 d without 2016), HD 122064 40 d (0.08), HD 143761 1.6 d
    (0.26). Log-log slope of coherence time vs BERV rate over 14 stars
    -1.04 [-1.84, +1.53] (-1 = BERV mismatch, 0 = fixed days); wide.
  - The same picture holds without 2016. tau Cet alone has too few pairs
    in the deciding cells (4.5-15 d, |dBERV| < 0.7: +0.08 [-0.93, +0.86]);
    the pooled result is driven by the slow-BERV stars.
- **Interpretation for tau Cet:** static observed-frame spectral
  structure that the star's lines cross as BERV changes, leaving a
  different error in each order: template mismatch (DSST, already
  suspected in 2016), iodine-model mismatch, or a residual
  detector/wavelength pattern. Not an instrument drift common to all
  orders, not the atmosphere, not a telescope. The weak cross-season
  repeat means the structure is not fixed for all time (era-dependent LSF
  or wavelength, or a template-iodine interaction), which the e2esim
  (+3.4 same-BERV cross-season) does not reproduce.
- **No hour-angle or airmass dependence:** tau Cet split at median |HA|
  +0.01 [-0.74, +0.83], at median airmass +0.31 [-0.41, +1.09]; across 17
  stars no consistent sign. (No ADC on MINERVA.) An iodine B-star frame was
  taken on 199 of tau Cet's 214 dates; on the other 15 the excess is 3.29
  vs 1.69 (-1.60 [-3.13, +0.33]).
- **Stricter telluric masks do not help** (paired, 352 exp / 214 nights):
  0.995 refit +0.12 [-0.13, +0.36], with multi-day coherence rising;
  orders 18-20 dropped -0.07 [-0.21, +0.07]; both -0.04. No independent
  clean telluric model exists in the test bed (its "clean" variant equals
  the production mask); NEID's L2 telluric model is the only candidate.
- **Water (spectral column; frame-name join, 332/352 matched, mid-times
  agree to 0.00 min):** dry vs wet nights 1.40 vs 2.09, +0.69 [-0.11,
  +1.49]; airmass-corrected +0.52; against the +/-15-day local median
  +0.35 [-0.48, +1.12]; variance model g = +0.35 per sd, p = 0.10. A
  floor(MJD) night key drops half the nights and exaggerates the split
  (1.04 vs 1.87). Water stays a weak suspect, not significant.
- **Week-long bootstrap blocks widen CIs 1.05-1.6x.** With 7-day blocks:
  Charlie -> v5 on x04 -0.71 [-1.38, +0.04] (no longer significant;
  2018-19 -1.14 [-2.06, +0.09]); no timing -> timing18 -0.61 [-1.09,
  -0.13] (survives; marginal on the original extraction). tau Cet level
  1.80 [1.31, 2.24]. Adopt 7-day blocks for headline comparisons.
- Ledger: `st_split_*`, `st_lagcov`, `st_absha_high`, `st_am_high`,
  `st_blk7`, `st_blk14`, `st_tell0995`, `st_drop1820`,
  `st_tell0995_drop1820`, `st_water_wet_*`.

## 2026-11-27: Instrument history from the project's meeting records

A timeline of ~1200 dated events (private) was compiled from the
project's meeting records. Facts that bear on the RV analysis:

- **Templates were already suspected in 2016:** the Keck DSST
  deconvolution was called the dominant error, adding ~1 m/s scatter
  correlated with the barycentric correction, and Keck-MINERVA template
  mismatch was raised again in 2017. This is the BERV-dependent mismatch
  the independent review points to.
- **No set-point step in 2016-04/05.** The only recorded 2016 enclosure
  set-point change is +2 C in late January (with the slit removed and the
  clock and DATE-OBS conventions fixed then). Candidates for the shared
  2016-05..06 drift: an extraction update (~04-08, older data left on the
  old reduction), exposure-meter-terminated exposures (~04-26), an NTP
  outage (03-29..04-15, +/-20 s), a second instrument's heat load and
  coupling to the vacuum chamber, and 2 C peak-to-peak room cycling.
- **Feed:** no scrambler, double scrambler or agitator was ever
  installed. The fibre assembly fitted at installation (2015-12, poor FRD,
  round-to-octagonal splices) appears to be the feed for the whole data
  set; it was re-polished and re-routed in early 2017 (throughput ~10x,
  telescope balance changed).
- **2017:** fibres re-polished; B-star cadence cut to one per night (B+I2
  frames absent 2017-03..09); a vacuum leak after an April outage with a
  2 px cross-dispersion shift and an IP change that did not recover; CCD
  to -80 C and chiller replaced in September. These explain why 2017
  behaves differently.
- **2018-09 trip** (not 2018-12): iodine cell back after an FTS rescan
  (the NIST 2018-08 atlas), all telescopes recollimated, mirrors cleaned,
  guide units refocused. The 2018-12 trip replaced guide cameras and
  repaired T3.
- **2019-09-18 and 2019-10-20 steps:** a guide-unit race condition fixed
  (one-image lag, wrong fibre position), room HVAC failure with a +1 C
  set-point change, then the iodine stage controller swapped with its home
  reversed.
- **Likely zero-point step not yet in the era list: 2021-05** (outage
  killed the thermal-control PDU; baseline temperatures shifted). Thermal
  control was degraded 2020-06..10 and 2021-05..09, and the room HVAC was
  dead 2023-06..2024-03.
- **The exposure meter was retired in 2021-09**; flux-weighted timing
  after that rests on guide images only.
- Air vs vacuum wavelengths were already flagged in 2016 (cf. the atlas
  air-dispersion finding).

## 2026-11-27: External precise RVs for 2016-2020 (stellar bound in MINERVA's worst era)

Public tables only, no spectra. Night-to-night = rms of nightly-mean
differences < 3 d apart / sqrt(2), not detrended: an upper bound on
star + instrument.

| Source | Star | Nights 2017-19 | Night-to-night 2017-19 (m/s) |
|---|---|---|---|
| HARPS RVBank v2 (Perdelwitz+2024, VizieR J/A+A/683/A125) | tau Cet | 33 | 1.1 |
| APF / HIRES, California Legacy Survey (Rosenthal+2021, J/ApJS/255/8) | tau Cet | 83 / 43 | 1.8 / 1.5 |
| same | sigma Dra | 154 / 23 | 2.2 / 1.0 (3 pairs) |
| same | HD 122064 | 69 / 4 | 1.7 |
| SONG iodine (Heeren+2023, J/A+A/674/A164) | sigma Dra | 375 | 2.5 |
| CORALIE (ESO reprocessing) | tau Cet | 113 | 2.2 |
| ESPRESSO GTO (Figueira+2025, arXiv 2507.07514) | tau Cet | 50 (2018-22: nightly rms 0.7 over 3.5 yr) | not computed |

- **tau Cet's stellar nightly term in 2017-19 is at most about 1 m/s
  (HARPS), and ESPRESSO's 0.7 m/s nightly rms over 2018-22 bounds it
  further.** With NEID's <= 0.6 for 2023-25, the star cannot supply most
  of MINERVA's 1.75 m/s excess in 2018-19.
- For sigma Dra and HD 122064 the bounds (1.7-2.2 m/s) include the other
  instruments' own floors, so they do not yet separate stellar from
  instrumental.
- Not obtained: ESPRESSO nightly RVs (DACE, manual download); the ESO
  HARPS DRS catalogue holds 69 tau Cet nights 2016-20 without spectra.
- Next: put HARPS / ESPRESSO / APF nightly means on MINERVA's nights and
  test whether MINERVA's nightly residual correlates with them (shared
  stellar signal) on overlapping or adjacent nights.

## 2026-11-27: CAMAL PWV from the CAMAL team's own reduction code (testbed branch camal-orig, 1c0cf56)

This replaces the crude reduction withdrawn on 2026-11-24. We reran the
CAMAL team's public reduction code (the code behind arXiv:1706.01798) on
the archived raw frames. The port to Python 3 is mechanical and scripted:
exact, asserted substitutions on the untouched originals (syntax, library
API moves, paths; upload/email/backup code removed). The algorithm is
unchanged, including a Python 2 dict-order bug that sometimes fits a star
with another star's temperature grid (13 nights, ~0.1 mm; flagged).

- **Coverage:** PWV for 128 of 143 archived nights (2017-05-12 to
  2018-06-09), 90,948 triplets; PWV 0.23-24.6 mm (5/50/95th percentiles
  1.25 / 3.91 / 12.3 mm). Every point carries flags for what had to be
  guessed or repaired: star temperatures from the target list (34
  nights), schedules rebuilt from frame names (56 nights the team never
  reduced), an opt-in fix for truncated triplets or unreadable files (46
  nights), a reseed on one night. 22 nights are entirely unflagged. No
  original output survives, so there is no direct check against the
  team's own numbers.
- **Against GPS:** Kitt Peak (53 nights, 2017): r = 0.45 per sample, 0.63
  for night means; CAMAL reads lower by a median 2.4 mm (Sep-Dec 2017
  -0.8 mm, robust rms 2.0 mm; May-Jul 2017 -3.8 mm, the nights with
  guessed temperatures and monsoon onset). Amado, at the foot of the
  mountain (8 nights): r = 0.70, reads ~4 mm above CAMAL as expected for
  the lower site. Kitt Peak has no 2018 Jan-Jun data.
- **Against our spectral water column:** r = 0.88 (Spearman 0.95; slant
  vs CAMAL x airmass 0.91; night means 0.90), but on only 19 exposures,
  11 nights. The spectral column tracks water after all; the earlier
  r ~ 0.3 was our photometry.
- **Against RV residuals (quick look, frozen v5 on x2-0.4):** 203
  exposures of 7 quiet or slow-orbit stars on 83 CAMAL nights (only 12 of
  tau Cet), 143 star-nights, residuals about each star-season median.
  r(night PWV, nightly residual) = +0.02 [-0.12, +0.15];
  r(PWV, |residual|) = -0.17 [-0.32, -0.02] (marginal; likely leftover orbits/offsets, not evidence that wet nights are better);
  wet-minus-dry excess +0.3 [-11, +12] m/s (useless: season-median
  residuals leave orbits and offsets in). Within nights (28 exposures
  with PWV within 30 min): slope -0.8 m/s per mm, r = -0.19. Night-block
  bootstrap CIs. Not ledgered: not an ML-excess run.

Verdict: CAMAL now exists as a calibrated-in-shape PWV series for
2017-05..2018-06, but its overlap with MINERVA RV exposures is small
(162 of 826 era exposures within 20 min) and the RV test is
underpowered. It neither confirms nor refutes a water effect; the earlier
tau Cet dry/wet split (wet 2.09 vs dry 1.40 m/s, +0.69 [-0.11, +1.49],
spectral column) remains the better-powered test: wetter looks worse, at
p ~ 0.1. The spectral column is
reinstated as a usable water proxy for the full baseline.

## 2026-11-27: Spectrograph thermal state and fibre illumination (testbed branch thermalillum, 9d95c8c)

Neither explains the excess. CIs are 7-day night-block bootstraps with all
stars resampled together; "per sd" means per standard deviation of the
covariate. Responses: exposure, nightly, within-night and order-differential
(odd-even, blue-red) residuals of 16 quiet stars, frozen v5 on x2-0.4.

**Thermal and pressure.** Enclosure logs (2020-2026), PT100 logs
(detector mount, camera, CCD coolant supply/return, optics) and
spectrograph/pump pressure, reduced to 1-minute means; atmospheric
pressure and humidity from headers. No channel is labelled G10.
- Positive control: the cross-dispersion trace centroid follows the
  detector-mount sensor at +0.34 [+0.25, +0.41] px/C (nightly r = +0.70),
  as the 4.4 um/C mount expansion predicts. Sensors and timing are right.
- But the RVs do not follow it: detector mount vs nightly residual
  +0.15 [-0.06, +0.65] m/s/C (tau Cet), +0.18 [-0.09, +0.64] (pooled).
  The iodine lines move with the stellar lines, so the predicted ~10 m/s
  for 0.03 C does not appear in the RVs (<0.02 m/s).
- 2,086 single tests (31 channels x mean / within-exposure change / rate,
  plus header values): 6.2% nominal p<0.05, none past Bonferroni. Joint
  6-PC model with week-wise 10-fold CV: held-out R^2 -0.008 pooled (null
  median -0.009, p = 0.44); tau Cet p = 0.73; order differentials
  p = 0.70-0.93.
- 95% bounds per channel: pooled nightly median 0.32, 90th pct 0.49 m/s;
  tau Cet nightly median 0.56, 90th pct 0.83 m/s.
- Weak leads, none surviving correction: enclosure humidity
  -0.28 [-0.44, -0.13] m/s per sd (same sign as the shared-term finding);
  sigma Dra alone joint p = 0.035 (held-out R^2 ~ 0).
- Wavelength-solution drift is not recoverable from the per-trace fits.

**Fibre illumination / scrambling.** Each telescope's RV minus the mean
of the other telescopes in the same exposure (cancels star, template and
BERV), demeaned per star x telescope x feed era, against per-telescope
illumination diagnostics from the extraction and guiding/seeing/focus/LSF
covariates.
- Real per-telescope effects: profile core excess vs the era profile
  -0.62 [-0.77, -0.50] m/s per sd (same sign on every telescope and star,
  strongest on T3; survives a throughput control); T3 fibre position
  -1.15 [-1.59, -0.77] (a nightly state); relative throughput
  +0.32 [+0.14, +0.49]. Higher throughput goes with less halo and a
  narrower LSF. Guide offset, guide rms, seeing and focus: |effect| <= 0.3,
  mostly consistent with zero, and they do not move the halo.
- Payoff (correction cross-fitted on alternate weeks, paired): tau Cet
  +0.00 [-0.05, +0.05] m/s; sigma Dra -0.05 [-0.16, +0.03]; HD 122064
  -0.05 [-0.17, +0.03]; pooled 16 stars -0.03 [-0.05, -0.00]. The
  per-telescope effects average down across telescopes; a six-term
  correction makes tau Cet worse (+0.23 [+0.00, +0.54]).

Verdict: thermal state is ruled out at the ~0.5 m/s level per channel.
Fibre illumination is real per telescope (fibre alignment and near-field
state, clearest on T3) and argues for a mode scrambler / cladding-mode
stripper on hardware grounds, but it is not the ~1.7 m/s excess.
Humidity remains a weak lead.

## 2026-11-27: Humidity (testbed branch humidity, 632bf62 pre-registration, 0f45659 code)

The vacuum tank is dry, but the fibres and camera see the room air. Sources:
outside RH from the site weather station (2016-02..2026-03, 99% of
exposures), spectrograph-room RH from the clean-room HVAC return air
(integer %, 2019-04..2024-03, 28% of exposures; clock drift fitted),
telescope-enclosure RH from headers. The header spectrograph-humidity
keyword is never filled. Correction to the thermalillum entry: its
"enclosure humidity" is the telescope enclosure 1 sensor, not the
spectrograph room.

- Room RH follows outside within ~1 h (peak r = 0.63) and is 93%
  explained by the outside water content at room temperature: the room
  has no humidity control.
- Seven tests were pre-registered (each needs p < 0.0071). CIs are 7-day
  night-block bootstraps; because humidity varies on months, each was
  also checked against the humidity series shifted by 30-365 d.

| Test | Effect | p (boot) | time-shift p |
|---|---|---|---|
| 16 quiet stars nightly vs 24-h outside RH | -0.23 [-0.39, -0.06] m/s per sd | 0.006 | 0.11 |
| tau Cet nightly vs 24-h outside RH | -0.30 [-0.61, +0.10] | 0.08 | |
| shared nightly term vs 24-h outside RH | r = -0.14 | 7e-4 | 0.01-0.03 |
| 16 quiet stars nightly vs 24-h room RH | -0.56 [-0.84, -0.26]; -1.07 per 10% RH | 1e-4 | 0.10 |
| per-telescope minus other telescopes | all within +-0.10 | 0.97 | |
| per-telescope profile core excess | r = +0.047 | 0.011 (fails) | |
| wet minus dry nightly excess | -0.10 [-0.46, +0.33] | 0.77 | |

- Best single predictor: outside RH at the exposure, -0.38 [-0.54, -0.20]
  m/s per sd (-0.26 per 10% RH, r = -0.11), time-shift p = 0.007; 14 of 15
  stars negative; also within nights. Longer leads are weaker.
- Room RH result is almost all 2019 (402 of 443 nights) and driven by
  tau Cet and sigma Dra; fitted with outside RH, they share it.
- No fibre-specific effect (excluded at ~0.3 m/s per sd); no sign of
  humidity-driven focal-ratio degradation; order differentials null.
- Not simple telluric water: same sign in all BERV terciles, and RH beats a
  slant water proxy when both are fitted.
- tau Cet wet/dry by outside RH: dry 1.68, wet 1.40 m/s, so it does not
  reproduce the spectral-water split (that column tracks slant water and
  room RH, r = 0.75 / 0.69, not outside RH, r = 0.36).
- Payoff (alternate-week cross-fit, paired): outside RH -0.011
  [-0.050, +0.026] m/s pooled, tau Cet -0.02 [-0.13, +0.12], sigma Dra
  -0.15 [-0.27, -0.03]; room RH (2019-24 only) -0.11 [-0.20, -0.00],
  probably one 2019 episode.

Verdict: a real but small common-mode humidity term (more humid, lower RV;
~1% of nightly variance), acting within about an hour on all telescopes
alike. It is not tau Cet's excess. If it matters for G-CLEF it argues for
humidity control around the fibre exit and camera.

## 2026-11-28: Chunk-by-chunk analysis (testbed branch chunks, 6a5762c)

A chunk is one telescope trace x one order (4 x 23 = 92), fixed in the
observer frame; its RV is the residual of the chain's level-1 joint fit
relative to the exposure RV (so it sees only chunk-specific error, not the
part common to all chunks). Base chain reproduces structure's series
exactly. CIs: 7-day night-block bootstrap; selections cross-fitted.

- **Chunk-specific error is a small part of the excess.** Errors
  independent across chunks add 0.30 [0.14, 0.35] (m/s)^2 for tau Cet
  against a chain excess^2 of 3.24 (9%, at most ~0.55 m/s in quadrature);
  1-5% for the other stars. That caps any mask.
- **It is real and shared at the order (wavelength) level.** Every star
  rejects equal chunks (p <= 0.023); split-half rho 0.3-0.65. Orders 17-20
  (Na D, water band) are worst for every star (order 19: 10-29 m/s chunk
  excess). Badness agrees between tau Cet and each solar-type star
  (Spearman +0.29..+0.48 against a ceiling of 0.57-0.75); shuffling traces
  within an order keeps it, so it is wavelength, not detector or fibre.
  HD 122064 (K4V) agrees with no one.
- **Chromatic slope in every star:** nightly RV-vs-wavelength slope excess
  4.9 [2.6, 6.1] m/s per 1000 A for tau Cet, 3.3-6.1 for the others.
- **BERV structure is strong, repeatable and wavelength-located** for
  tau Cet (cross-season Z +34.6; null 95% [-4.8, 5.7]; 75 of 92 chunks at
  q < 0.1) and sigma Dra (+19.4); weak elsewhere. Curves agree across the
  four traces of an order (0.47) and not across orders of one trace
  (-0.03). It does not transfer between stars, and on the same night
  chunk residuals of different stars are uncorrelated. Feature map:
  peaks are not enriched on telluric lines; features that persist under
  both templates include a shallow telluric line at 5077.24 A
  (T = 0.983, just above the 0.98 mask) and the window edges of orders
  19, 20 and 23, where stellar lines cross the fixed window.
- **No out-of-sample payoff** (tau Cet, season split): weight by chunk
  excess +0.00 [-0.08, +0.12]; mask 9 worst +0.14 [-0.04, +0.32];
  spline-correct 9 worst BERV chunks -0.06 [-0.23, +0.14]; mask 9 worst
  BERV chunks +0.04 [-0.11, +0.22]. Transfers between stars null both
  ways. In-sample greedy dropping of 20 chunks gives 1.80 -> 1.15
  (-0.65 [-1.01, -0.27]) but +0.09 [-0.23, +0.48] held out: the size of
  the overfitting trap.
- **NEID template (dsst_cs vs neid_cs):** chain excess 1.79 -> 1.76;
  chunk-specific variance falls ~40% (0.27 -> 0.16) and the chromatic
  slope 5.0 -> 3.1, but the bad chunks stay (per-chunk excess rho 0.88,
  BERV strength rho 0.87, at the reliability ceiling) and ~88% of the
  repeatable BERV structure survives (Z 32.8 -> 28.8). The
  template-dependent part is ~16% of the BERV-curve variance.

Verdict: the bad chunks are fixed in wavelength and common to the G/K
dwarfs, not tau Cet's DSST template; the BERV structure is mostly
template-independent. But chunk-specific error is only ~9% of tau Cet's
excess, so masks and weights cannot recover it; the rest is common to all
chunks (possibly chromatic). The 5077 A line was already inside the 0.995
mask test (structure entry: +0.12, no gain).

## 2026-11-28: NRES rescue, first pass (branch nres, 9b31c79)

LCO's NRES (R ~ 53,000, simultaneous ThAr fibre, 1-m telescopes at four
sites) stopped operating on 2026-08-01; it is specfast's third instrument,
an archival test bed for the no-gas-cell calibration path. Scoping found
that the public BANZAI-NRES pipeline never uses the simultaneous ThAr
fibre (each frame takes the nearest afternoon arc's wavelengths), fits each
arc from scratch as one unweighted 2-D polynomial per fibre, uses a
logg 5.5 PHOENIX template for every dwarf (sometimes misclassified),
uses 21 of 67 orders, and takes each order's CCF maximum without a peak
fit. Its quoted errors do not describe the night-to-night term.

**E0, cleaned archive RVs** (tau Cet, sigma Dra, HD 26965, 2020-2025; 157
spectra; flags fixed in advance: wrong template 6, S/N < 30 8, stale arc
> 3 d 35, calibration failure 24; 96 clean on 51 star-nights; zero-points
per site and science fibre; 7-day block bootstrap):
night-to-night 29.1 [19.1, 35.3] m/s (CPT 18, ELP 34, LSC 24, TLV 37);
within-night 12.2 [8.5, 15.2]; fibre 0 - fibre 2: CPT -51, ELP +156,
LSC -182 m/s.

**E1 + E2 pilot** (tau Cet, LSC 2022, 10 exposures on 5 nights, both
fibres; RVs from the template module in infer mode, wavelengths fixed per
variant). E1: static reference line positions, a low-order per-arc shift
shared by all lit fibres, one dispersion law m*lambda = P(x, m) on the
ThAr fibre and a static offset map per science fibre (0.059 px per line
arc to arc, 1.5-2 m/s per arc). E2: frame-to-frame drift from the ~900
simultaneous ThAr lines (5-6 m/s per 143-s frame), relative to a static
science-vs-arc offset per unit, era and fibre.

| method | night-to-night | paired vs archive | within-night | fibre 0 - 2 |
|---|---|---|---|---|
| archive (BANZAI CCF) | 18.3 | | 10.3 | -153 |
| specfast, BANZAI wavelengths | 14.3 | -4.0 [-5.9, -0.7] | 3.2 | -159 |
| E1 | 13.7 | -4.7 [-15.2, +1.9] | 3.2 | -396 |
| E1 + E2, drift averaged per night | 4.9 | -13.4 [-18.6, -1.0] | 3.2 | -395 |

- Night-to-night: promising (18 -> 5 m/s, paired) but five nights at one
  site; the network go/no-go waits for the full three-star run.
- The fibre split grows, not vanishes, once both fibres are on one
  ThAr-consistent scale: BANZAI's arc solutions are biased by +66 to +230
  m/s depending on fibre and era, which partly cancelled a real ~-395 m/s
  displacement of starlight relative to lamp light. In the pilot, fibre 0
  and fibre 2 were used in different months, so fibre and era are
  confounded; the two-fibre sites can separate them.
- Re-extraction from raw was not needed for the pilot.

**TESS inventory (partial, 2016-01..2020-10 only):** 27,975 public NRES
science exposures, 6,494 matching 443 TOI hosts; 219 targets with >= 5
nights, 59 with >= 10; 5,425 matched exposures have raw frames but no
BANZAI product (mostly 2018-19). Counts are lower bounds.

The archive rate-limited anonymous access mid-download; the full E0-E2
run on all three stars and sites is scripted to resume.

## 2026-11-28: NEID-built template for tau Cet (testbed branch neidtemplate, 99cf2b9)

Template: 48 public NEID L2 HR spectra of tau Cet (extsnr >= 280, one per
night, BERV -27..+18 km/s), telluric-corrected and masked, shifted to rest,
co-added, continuum from DSST on scales > 10 A only, deconvolved by the
width fitted against DSST (relative sigma 0.896 km/s; NEID's nominal LSF
is 1.14, so DSST looks under-deconvolved by ~0.7 km/s in quadrature),
placed on DSST's frame and cell-averaged as in the chain. Co-add vs DSST
0.76% rms (Mg b 2.4%); DSST has a ~0.2 km/s velocity tilt across the band
against NEID's comb wavelengths (absorbed by per-order zero-points).

Frozen v5 on x2-0.4, 352 exposures, 214 nights, paired 7-day block CIs:
- **ML nightly excess: 1.79 -> 1.76 m/s, -0.03 [-0.22, +0.18].** No era
  moves; point-sampled pair the same; dropping Na D changes nothing.
- Lag <= 1.5 d covariance -0.19 [-0.42, +0.03]; BERV-matched and
  cross-season covariances, BERV slope and cubic-in-BERV rms
  (0.46 -> 0.37) all unchanged within CIs.
- **The order split changes:** common/total excess variance rises
  odd/even 0.41 -> 0.69 (+0.29 [+0.02, +0.70]) and blue/red 0.19 -> 0.63
  (+0.44 [+0.01, +1.29]); each half's excess drops while the full excess
  stays. DSST added order-specific errors that average out across orders;
  what remains is closer to achromatic. This weakens the structure
  entry's "tau Cet's excess is order-specific".
- Per-trace fits: lower reduced chi2 on 96% of 19,558 traces (median
  4.51 -> 3.92); Mg b order 11.3 -> 4.2 (a DSST defect).
- **Residual stack** (persistent rms, 1e-3 of continuum, DSST / NEID):
  observer frame 5.2 / 5.4; detector 3.6 / 3.6; stellar 3.6 / 2.5. The
  observer-frame pattern is the same in all four telescopes (between-
  telescope covariance equals within-telescope persistence) and is not on
  the detector (the pixel-wavelength mapping moves 6 km/s per trace, yet
  detector-frame persistence is lower). The template error is the stellar-
  frame part and falls with NEID, mainly in orders 14-20. What remains
  fixed in wavelength points to the iodine model/LSF or telluric residuals;
  its RV impact is not established (residuals are orthogonal to the
  velocity derivative).

Verdict: the stellar template is not what limits tau Cet. NEID fits better
and removes the template's order-specific errors, but the excess is
unchanged at ~1.8 m/s, now closer to achromatic. Together with the chunk
analysis, the remaining excess is common across orders and telescopes.

## 2026-11-28: Stable-line atlas from NEID solar data (specfast branch lineatlas)

Question: are some solar absorption lines individually stable (in both
NEID eras and at low and high activity), and does restricting to or
weighting by them lower RV scatter on the Sun and on tau Ceti?

**Literature first.** Line selection in Sun-like stars typically buys a
factor ~1.5-2 in rms on HARPS alpha Cen B (Dumusque 2018; Cretignier et
al. 2020: uncorrelated lines 0.89 vs ~2.1 m/s; Siegel et al. 2022: 2.67 ->
1.29 m/s) and 44% on the NEID Sun with an aggressive scatter-minimising
selection of 24 of 3830 line/order pairs (Pandey et al. 2026, FLARES,
2.01 -> 1.12 m/s). Activity sensitivity scales inversely with line depth
and with formation temperature (Cretignier 2020; Al Moulla et al. 2022,
2024). Only FLARES publishes a per-line solar table (Zenodo
10.5281/zenodo.20937741, CC BY 4.0); the Geneva and Siegel line tags are
not public. ESPRESSO masks ship with the ESO pipeline; the NEID DRP masks
are not publicly hosted.

**Data.** 120 new NEID solar days, 2021-01 to 2026-11 (two per month,
chosen from archive metadata by frame count and span only; 10 frames
spread over each day), plus the six 40-frame days of the earlier test,
streamed into compact caches (orders m = 154-79). RV-blind cuts: comb
wavelength calibration only (eight "ThAr-only" days sit ~30 m/s off in
NEID's own CCFs as well), S/N >= 150, exposure-meter flux variability
<= 0.27 (clear sky 0.245-0.255) and S/N >= 0.8 x the day's best (clouds),
>= 4 good frames, and NEID's CCF velocities consistent within the day
(robust sd <= 3 m/s; catches feed or instrument glitches such as
2021-10-24 at +150 m/s, independently of any line choice). 767 frames on
77 days remain (25 pre-fire, 52 post-fire). One template per NEID master
wavelength file (pre-fire; post-fire 20201216, 20240902, 20260130 and
20260920 / DRP v1.5.4), per-line zero points per template era plus a
break at 2024-03-01.

**Method.** `specfast.doppler.lbl`: median co-add template per order with
per-frame continua; 17,331 line windows between the template's maxima;
per-line velocity = projection of the residual on dT/dv (Bouchy 2001,
Dumusque 2018, Artigau 2022). Clean lines: NEID telluric model < 1%
anywhere in the window in every frame, measured in >= 90% of frames,
FWHM >= 4 km/s, median per-frame error <= 100 m/s (8,370). Lines combine
per frame with 5-sigma clipping. The robust combination matters: on tau
Ceti a plain weighted mean of all lines gave 2.75 m/s nightly in a first run, because a
few red-order lines (sky emission, tellurics) are off by tens of m/s.
Per line: an unbiased day-to-day excess variance (mean of D^2 - E^2 over
era-centred daily means), on pre-fire, post-fire, low- and high-sunspot
days separately; within-day excess; slopes against the common daily RV
(beta) and the sunspot number. "Universal" stable: excess below the
clean-line median in all four subsets. Cross-fit: alternate days in each
era form two halves; select on one, evaluate on the other, both ways;
2000 day-bootstrap resamples, paired.

**The LBL velocities.** Daily rms 2.11 m/s with all clean lines (NEID DRP
CCF 2.94 on the same days); per exposure the LBL matched the CCF to
0.25 m/s on three clean 2021 days (first test). Within eras the daily RV tracks the sunspot
number (r = 0.48, 2.7 m/s per 100 SN; 2.11 -> 1.85 m/s after regression).

**Per-line statistics.**
- Per-line excess is large and repeatable. The median clean line
  scatters 11 m/s day to day beyond photon noise; 44% have an excess
  above 3 sigma, 22% are consistent with zero. Spearman of per-line excess
  between disjoint day halves 0.78, pre- vs post-fire 0.63, low vs high
  activity 0.76. Universal sets chosen on the two halves share 2,092 lines
  against 869 by chance. **So some lines are "universally" more stable.**
- What predicts stability: depth above all (photon-weighted mean excess
  1475 (m/s)^2 at depth 0.03-0.1, 404 at 0.1-0.2, 143 at 0.2-0.4, 57 at
  0.4-0.6, 38 above 0.6), then width (broader is better) and blending; it
  is higher at 4500-5500 A, rises weakly with excitation potential
  (Spearman +0.13) and does not depend on the Lande factor (atomic data
  from VALD via FLARES, 2,950 matched lines).
- Per-line activity response is not measurable line by line here: beta
  and the sunspot slope are not repeatable between halves (Spearman 0.13,
  0.10). Binned by depth, shallow lines follow the common daily RV less
  (beta 0.62 at depth < 0.1, 0.81 at 0.1-0.2, ~0.9 deeper).
- The universal set (all days) is 3,065 of 8,370 clean lines (37%) but
  carries 81% of the photon weight: the unstable lines are mostly the
  shallow ones that photon weighting already down-weights.

**Payoff (m/s, 95% CIs).**

| | Sun, daily rms (cross-fit, 77 days) | diff vs all | tau Cet, nightly rms (25 nights) | diff vs all |
|---|---|---|---|---|
| all clean lines | 2.01 [1.61, 2.38] | | 0.647 [0.45, 0.81] | |
| universal stable set | 1.96 | -0.05 [-0.15, +0.05] | 0.605 | -0.04 [-0.10, +0.04] |
| lowest-excess 50% | 1.98 | -0.04 [-0.11, +0.03] | 0.610 | -0.04 [-0.10, +0.04] |
| lowest-|beta| 50% | 1.99 | -0.02 [-0.08, +0.05] | 0.621 | -0.03 [-0.07, +0.03] |
| excess-variance weights | 1.99 | -0.022 [-0.042, -0.005] | 0.662 | +0.01 [-0.00, +0.04] |
| FLARES top 24 (40 windows) | 2.21 (all days) | +0.10 [-0.24, +0.51] | 0.965 | +0.32 [+0.04, +0.58] |
| FLARES top 10% (467) | 1.97 (all days) | -0.14 [-0.26, -0.03] | 0.679 | +0.03 [-0.10, +0.17] |
| NEID DRP CCF | 2.94 | | 0.717 | |

tau Ceti uses the solar selection from all solar days (no tau data in the
choice). The FLARES rows on the Sun are not out of sample: FLARES was
selected on 2021-2025 NEID solar data that overlap these days.

- **The stable subset buys 2-7% at most, not significant on either star.**
  Per-line excess is mostly independent between lines, so it averages
  down over thousands of lines (~0.1 m/s), while the 2 m/s daily scatter
  is common to all lines and about half of it tracks solar activity. A
  selection only helps if lines differ in their response to the common
  term, and that response cannot be measured line by line at this S/N.
- Published lists do not transfer cleanly: FLARES's 24 lines are
  photon-limited on tau Ceti and not better on the independent part of
  the solar data; its top 10% helps on the Sun (partly in sample) and not
  on tau Ceti.

**MINERVA.** Every line in 500-620 nm carries its MINERVA order (tau Cet
frame). Per order, the share of stable-line information against tau Cet's
chunk-specific excess (chunk-by-chunk entry): Spearman +0.36 (p 0.09; a
benefit would be negative), stable fraction +0.24 (p 0.27). Stable lines
do not explain MINERVA's bad chunks, consistent with that entry's finding
that chunk-specific error is ~9% of tau Cet's excess.

Verdict: individually stable solar lines exist and are the same in both
eras and at both activity levels, but restricting or weighting to them
does not lower the daily or nightly RV scatter measurably; the remaining
stellar term is common to all lines. For NEID, NRES and G-CLEF the useful
products are the line windows and the robust LBL combination (0.65 m/s
nightly on tau Ceti vs 0.72 for the DRP CCF), not a stable-line mask.

Atlas: `data/neid_solar_line_atlas.csv` (10,265 rows: clean lines and
resolved telluric-flagged lines). Columns: NEID order m; rest vacuum
wavelength in the solar template frame and window edges (A); depth; FWHM
(km/s); blend (1 - lower flanking maximum / continuum); `tell_max` (max
NEID telluric absorption in the window over all solar frames); `clean`;
median per-frame error (m/s); day-to-day excess variance ((m/s)^2,
unbiased, can be negative) on pre-fire, post-fire, low- and high-activity
days and all days, with its standard error; within-day excess variance;
`beta` (slope vs the common daily RV) and the slope vs sunspot number
(m/s per 100), with errors; excitation energy, log gf and Lande factor
where a FLARES line matches within 1 km/s (VALD via Pandey et al. 2026,
CC BY 4.0); MINERVA order (1-23, -1 outside); `stable` (universal set on
all days); `flares_top24`. Species identifications are not included.
Code: `scripts/neid_lbl_cache.py`, `scripts/neid_lbl.py`,
`scripts/neid_lineatlas.py`; ledger rows `la_*`.

## 2026-11-25: Autofocus-in-exposure spectra: keep and correct (testbed branch afexp)

Question (JDE via the robofast session): are the 2016-04..2020-01 spectra
with autofocus inside the exposure worth keeping?

- **The damage is a common-mode timing shift.** Autofocus usually hit
  every telescope of an exposure (tau Cet: all four in 30 of 44
  four-telescope exposures). Affected vs matched unaffected exposures on
  the same night: tau Cet 2018-19 affected sit +1.52 [+0.04, +3.35] m/s
  high with no timing correction, +0.38 [-0.19, +0.97] with the FAU-flux
  correction, and affected scatter matches unaffected (z rms 0.85 vs
  0.79). No telescope-specific excess for any star (tau Cet z rms 0.97 vs
  0.95, extra scatter 0.00 [0, 0.39] m/s).
- **Which flux record:** any record that treats the autofocus span as
  zero light into the fibre fixes the offset; the exposure meter is best
  (offset -0.03, z rms 0.81 vs 0.88). Counting the autofocus frames as
  ordinary guider flux does not (+1.47, as bad as uncorrected +1.51).
- **No illumination effect:** after correction, residuals don't track
  the defocus step, when autofocus ended, the affected fraction, guide
  offsets or gaps, or airmass (|rho| <= 0.10, p >= 0.11).
- **Options on tau Cet:** dropping the affected telescopes loses 41 of
  207 nights and worsens fixed-weight nightly rms by +0.37 [+0.07, +0.70]
  m/s (held-out half +0.42); inflating their errors gives no real gain.

Decision: keep them, with a per-telescope flux-time record that sets the
autofocus span to zero fibre flux (exposure meter where alive). 2016-17
are thin and the pre-2018 guider-flux amplitude is only partly supported
(timing re-validation), so use the exposure-meter record there. HD 122064
in 2017 is the one hint of residual scatter (12 exposures, not
significant).

## 2026-11-25: The 2016 deficit of x2-0.4: not the flat, partly the wavelength solution (testbed branch flat2016)

Follow-up to the paired finding that x2-0.4 is worse than the original
extraction in 2016 only (sigma Dra +0.95, HD 122064 +1.00 m/s ML excess).
Frozen v5 chain, each variant's 2016 rows replacing x04's, paired
night-block bootstrap on the same 2016 exposures (ML excess difference,
m/s, 95% CI):

| 2016 | x04 vs original | no pixel flat vs x04 | original wavelength solution vs x04 | both vs x04 |
|---|---|---|---|---|
| sigma Dra (146 exp, 53 nights) | +0.95 [+0.66, +1.24] | +0.11 [+0.06, +0.15] (worse) | -0.17 [-0.24, -0.09] | -0.06 [-0.12, +0.01] |
| HD 122064 (112 exp, 42 nights) | +1.00 [-0.01, +1.91] | -0.05 [-0.14, +0.01] | -0.16 [-0.31, -0.03] | -0.18 [-0.37, 0.00] |
| tau Cet (22 exp, 11 nights) | +0.88 [0.00, +3.68] | n.s. | n.s. | n.s. |

- **Not the flat.** The original pipeline never pixel-flat-fielded (no
  flat division in v0.1-v0.4.1; v1.0.0 resets its flat to ones), so "the
  original's flat" is "no flat", and removing x04's flat makes sigma Dra
  slightly worse. 2016 has no usable slit flats (Jan-Jun flooded at
  52-56k ADU; Aug-Nov lamp off). The 2018-19 stack agrees with 2016 fibre
  flats as well as with post-realignment ones, and changes extracted flux
  by only ~0.1% per pixel.
- **The wavelength solution is a small real part.** The original 2016
  products' solution differs from the v1.0.0 solution x04 uses by 0.57 px
  rms, per-order offsets spread over ~114 m/s, identical in every frame
  (from 2017 on the two are identical). Using the original solution
  recovers ~15-20% of the deficit for sigma Dra (wrms -0.12). For HD
  122064 the gain is offset by harm to unchanged 2017 exposures through
  the chain's shared offsets, so it is not reliable.
- **~80% of the 2016 deficit is unexplained.** x04 has much lower 2016
  within-night scatter (HD 122064 5.39 -> 2.79) but more night-to-night
  excess: an error coherent within a night, consistent with a profile or
  trace-file effect. Next: the e2016a self-profile vs a fibre-flat
  profile, and the 2016 trace file vs the original's 2016-01-30 traces.

Decision: keep x04's 2016 flat; no archive re-run yet.

### Follow-up: fibre-flat profile and reference traces (flat2016, 278701f)

Same frozen chain and scoring, on the 402 frames taken before the
2016-11 realignment. Two variants:
- **fprof:** the fibre-flat profile replaces the 2016 self-profile.
- **trv02:** reference traces rebuilt the way the original v0.2 built
  them, from the four 2016-01-30 fibre flats, with a centre every 20
  columns and a 6th-order polynomial per trace. 94 of 116 traces were
  refitted; the faint and edge traces are kept.
  - They differ from x04's 2016 trace file mainly by per-trace offsets
    (median -0.28 px, up to 1.8 px), which x04's per-frame re-centring
    absorbs.
  - After removing a constant and slope per trace, the shapes differ by
    only 0.014 px (median), at most 0.06 px.

ML excess change vs x04, m/s, 95% CI:

| 2016 | fprof | trv02 |
|---|---|---|
| sigma Dra | -0.23 [-0.40, -0.12] | **-0.36 [-0.51, -0.25]** |
| HD 122064 | +0.03 [+0.01, +0.06] | -0.06 [-0.13, +0.01] |
| tau Cet | 0.00 | -0.01 |

- **Neither variant harms the exposures it leaves unchanged.** 2017 and
  later move by at most ±0.04 m/s.
- **The traces are the biggest lever found for 2016.** Once re-centred,
  trv02's final centres differ from x04's by only ~0.02 px rms, yet
  sigma Dra's excess moves by 0.36 m/s. The 2016 RVs are sensitive to
  trace-shape differences below 0.05 px.
- x04's 2016 trace file needs larger per-frame shifts than trv02 does
  (0.25 vs 0.17 px rms), so it matches the early-2016 frames worse.
- **Still unexplained:** relative to the original extraction, sigma Dra
  is +0.59 [+0.26, +0.93] m/s worse with trv02 and HD 122064 about
  +0.9. That is about 60% of sigma Dra's deficit and most of HD
  122064's.

**specfast requirement:** the trace reference must match the epoch
(rebuilt after every optical change). Trace-shape differences of
~0.02 px after re-centring reach the RVs at the 0.3 m/s level.

**Combinations (flat2016, 8460045).** ML excess change vs x04, m/s, 95%
CI:

| 2016 variant | sigma Dra vs x04 | sigma Dra vs original | HD 122064 vs x04 | HD 122064 unchanged 2017-03..12 |
|---|---|---|---|---|
| trv02 | -0.36 | +0.59 | -0.06 | -0.02 |
| trv02 + original wavelength | **-0.52 [-0.66, -0.38]** | **+0.43 [+0.14, +0.79]** | -0.15 [-0.25, -0.04] | **+0.34 [0.00, +0.77]** |
| per-frame traces (trfr) | -0.33 | +0.62 | -0.08 | -0.02 |
| trfr + original wavelength | -0.47 | +0.48 | -0.17 | +0.34 |

- **For sigma Dra the effects add** (-0.36 and -0.17 give -0.52).
- **The original wavelength solution always costs HD 122064's unchanged
  2017 exposures** (+0.31 to +0.75 across every variant that uses it).
  It acts through the era offsets the chain shares across eras. tau Cet
  2016 also gets slightly worse (+0.19, 11 nights).
- **Re-measuring the traces on every frame is no better than the static
  v0.2-style traces.** The lever is the reference trace shape, not
  per-frame tracking. That qualifies the requirement above: what
  matters is a trace reference that matches the epoch.

Decision for an x2-0.5 2016 re-extraction (not run): use trv02. The
original wavelength solution goes in only if the chain gets an
independent 2016 offset, so it can't leak into 2017.

Still unexplained: in 2016, relative to the original extraction,
sigma Dra is +0.43-0.59 m/s worse and HD 122064 about +0.85. Not
explained by the flat, the profile, the traces or the wavelength
solution.

## 2026-11-25: Why autofocus ran inside exposures, and why the FAU status keyword can't flag it

Of 789 (exposure, telescope) cases in 2016-2020 where a FAU autofocus run
ends inside a tau Cet, sigma Dra or HD 122064 exposure, the header's FAU
status at shutter open reads GUIDING in 760, ACQUIRING in 18 and is
missing in 11. A filter on that keyword would remove almost none of them.

Cause, from the legacy control code's history: from 2016-04 to 2020-01 each
telescope's thread ran coarse acquisition -> fine acquisition (which sets
the "acquired" flag) -> autofocus -> guiding. The spectrograph waited only
for every telescope's "acquired" flag, so the exposure started right after
fine acquisition and the autofocus ran during it, while the status
keyword (written at exposure start from the acquired and guiding flags)
read GUIDING. The guiding step then reset and re-acquired mid-exposure. A
2020-01 change put autofocus first and dropped the separate fine
acquisition, so from then on autofocus inside an exposure needs the
acquisition timeout to expire. (2018 headers also carry a misspelled
duplicate status keyword with the same values.)

Consequence: for 2016-04..2020-01 data the FAU status keyword cannot
identify affected telescopes; the FAU autofocus records or the guide-image
flux record are needed. specfast should take the per-telescope flux-time
record as the timing input and treat header status keywords as hints only.

## 2026-11-25: Spectrograph temperature sensors vs RV residuals (testbed branch thermal)

Sources: the PT100 logs (four 4-channel loggers, ~10 s sampling, 2016-02 on)
and the thermal-enclosure controller logs (2015-01 to 2019-12; the live
thermal-log share was unreachable). Channel map from the logger configs:
A1/A2 echelle side/top, A3 optical bench, A4 air in vacuum, B1 iodine-cell
enclosure (~27.8 C; not the 55 C cell heater), B2 input optics, B3/B4 CCD
water supply/return, C1 vacuum input window, C2 CCD shutter, C3 CCD mount,
C4 camera, D1 top of grism, D2 CCD invar table leg, D3 CCD housing, D4
vacuum input port (2016 only); enclosure air, table, HVAC and collimator
channels. Coverage of tau Cet exposures 93-96% in every era. Thermal
history: 25.06 +- 0.002 C per day until 2019-01; 24.5-25.9 C with 0.1-1 C
night-to-night swings from 2019-09; 21.7 C in 2020-09; ~25 C in 2022;
uncontrolled 20-23.7 C in 2024-26 (these excursions give the test power).

Header caveats: TEMPA1..D4 are single 10-s samples taken 0-25 s before the
exposure starts, not exposure averages. **The TEMPE01..12 header labels
are wrong**: the legacy control code reads column i+4 but labels it with
config entry i, so every label is shifted by four channels (TEMPE01,
labelled "air top south corner", is the outside average).

Method: per exposure, the sensor mean over the exposure, change within
it, dT/dt, change since the start of the night and change of the nightly
mean since the previous night; nightly weights 1/(e^2 + 1.8^2); residuals
and covariates detrended with a +-15-day running median, nights permuted
within era; family-wise correction over 140 tests per (star, era) and 24
families (2,744 tests in all). Inter-sensor correlation makes the null
count of nominal p < 0.05 hits large (median 58, 95th percentile 134 of
1,820); 187 observed is within it.

- **No sensor explains the nightly or within-night residuals** of tau Cet,
  sigma Dra or HD 122064: best corrected p 0.46 (nightly), 0.74 (within).
- **Echelle** (A1/A2), nightly, detrended: tau Cet +0.30 +- 0.38 m/s per C
  overall; 95% upper limit on its contribution 0.50 m/s (0.58 in 2018-19,
  1.1 in 2020+; only ~2 m/s in 2016-17, when the sensors barely moved).
  Held-out variance explained ~0.
- **Only lead, slow and confounded:** the 2016-04 enclosure set-point step
  (25.18 -> 24.96 C) coincides with a sigma Dra / HD 122064 drift
  (Feb-Jun 2016); it does not survive detrending or the correction.
- **No shared nightly shift between stars** observed on the same night
  (detrended): tau Cet x sigma Dra r = -0.09 (45 nights), tau Cet x HD
  122064 +0.05 (16), sigma Dra x HD 122064 -0.10 (51). If the ~1.4 m/s
  term were a nightly instrument state shared by all stars, tau Cet x
  sigma Dra would show r ~ +0.2.
- **Not random clock offsets.** A nightly clock error would scale with
  dBERV/dt; an ML fit of the nightly excess as a + sigma_t |dBERV/dt|
  gives no gain for tau Cet (sigma_t 7.5 s, dlnL 0.00) or sigma Dra, whose
  dBERV/dt is near zero yet whose excess is 3.1 m/s.

**Implication.** The ~1.4 m/s unexplained term is common to the four
telescopes but not to the stars observed that night: it lives in the
exposure of one star, not in a nightly instrument state. Candidates:
the star itself (NEID bounds tau Ceti at <= 0.6 m/s), or something
per-exposure and fibre-common that depends on that star's spectrum or
pointing (template x exposure conditions, per-exposure iodine/LSF/
wavelength freedom interacting with the star's lines).

## 2026-11-25: Iodine-cell temperature and the barycentric timing model

**Iodine-cell temperature vs nightly residuals** (x2-0.4 v5c nightly means,
weighted with the 1.8 m/s excess added in quadrature, permutation p):
tau Cet r = +0.01 (p = 0.93); sigma Dra +0.24; HD 122064 -0.09. The
logged cell temperature (I2TEMPA) has 0.1 C resolution and sits at the 55.0
C set point in 71% of exposures (range 54.6-55.2), so the test only rules
out a strong effect at the >0.1 C level. The permutation p for sigma Dra
overstates significance: its residuals have ~2 m/s red noise, and any
slow covariate correlates with them. The iodine-stage position (I2POSAF)
takes four values that change at 2016-12, 2019-10 and 2022-07, i.e. it is an
era marker already covered by the era zero-points; its residual
correlations (sigma Dra -0.30, HD 122064 -0.36, tau Cet +0.03) are
era-level, not nightly. tau Cet's nightly residuals show weak
correlations with CCD temperature (+0.16) and exposure time (-0.16); none
with bench temperature or spectrograph pressure.

**How timing enters the barycentric correction.** The test bed evaluates
the barycentric correction once, at the geometric midpoint, and the timing
correction shifts it to the flux-weighted midpoint, linearly (dv =
dBERV/dt x dt). It does not integrate the correction over the flux-time
profile. The neglected curvature term is 1/2 BERV'' var(t); for a uniform
exposure it is small: tau Cet (median 906 s) rms 0.03 m/s (range -0.06 to
+0.18), sigma Dra and HD 122064 (1800 s) rms 0.06-0.07 (up to +-0.14).
Gappy profiles change var(t) but keep it at the ~0.1-0.2 m/s level, far
below the ~1.4 m/s common term. For the mm/s goal it must still be done
properly: specfast releases raw redshifts with the flux-time record, and
EXOZIPPy's raw-redshift mode integrates the correction over it.

## 2026-11-25: End-to-end simulation of the tau Cet data set (testbed branch e2esim)

Question: can the v5 analysis chain by itself produce tau Cet's 1.78 m/s
common nightly excess?

**Simulation.** All 358 x2-0.4 tau Cet exposures rebuilt trace by trace
with their real headers, BERV, masks, flux, blaze and read noise; constant
true RV; fitted by the unchanged test-bed code and v5 chain (without the
timing and T2 regressions, which correct real effects). Truth: the real
fitted wavelengths with D and the static table S; NIST iodine interpolated
in optical depth on a 0.02 km/s grid; the per-era B-star LSF maps with
h3/h4; photon + read noise; the star = a stack of all 132 NEID tau Ceti
L2 frames with NEID's LSF removed (Wiener filter), which differs from the
DSST template by ~1% rms; tellurics from a fit to NEID's per-frame
telluric models with a random nightly water column. (A first round with
the Hinkle/Wallace telluric atlas injected fake micro-tellurics from the
atlas's own sub-1% noise: 4.04 m/s with a BERV slope the real data lack;
superseded.)

| Run | ML nightly excess (m/s) |
|---|---|
| real data, same chain | 1.78 [1.62, 1.95] |
| simulation, full | 1.97 [1.82, 2.14] (second seed 1.93) |
| noise only | 0.00 [0, 0.25] |
| truth star = DSST (no template mismatch) | 0.69 [0.53, 0.84] |
| half the template mismatch | 1.30 |
| iodine on the model's 0.25 km/s grid | 1.86 |
| LSF = the model's Gaussian | 1.75 |
| no tellurics | 2.13 |
| no static wavelength table S | 1.74 |
| + real-like per-exposure LSF variation | 2.14 |

Quadrature attribution: template mismatch 1.85; static wavelength table
0.92; static LSF asymmetry (h3/h4) 0.90-0.94; iodine atlas representation
0.65; tellurics ~0; real-like LSF variation 0.84 (the only term with a
per-telescope part). The simulation reproduces the real trace-level misfit
(median chi2_r 4.41 vs 4.61).

**Same size, different kind.** In the simulation the analysis error is a
fixed function of BERV: BERV-binned leave-one-out means explain 62% of it
(75% of the template part). In the real residuals the same test explains
only 10-16%. Even half the template mismatch leaves the series 41%
BERV-coherent, so the real template mismatch is at most ~0.4-0.5 of the
simulated one (the truth spectrum's own ~1% errors likely inflate it). The
simulated analysis error correlates with the real nightly residuals at r
~ +0.2-0.3, i.e. ~0.6-0.8 m/s of the simulated pattern is in the data.

**Conclusion.**
- The analysis accounts for ~1.0-1.2 m/s of the 1.78: non-template terms
  (S, LSF asymmetry, atlas, ~0.7 together) plus a template term of at most
  ~0.8.
- **~1.4 m/s is not produced by any simulated analysis term**: random
  night to night, common to all telescopes, not a function of BERV.
  Suspects: something shared by all fibres that changes nightly (the
  iodine cell or spectrograph state; shared timing or shutter;
  per-exposure detector-map changes common to all fibres; something in
  the extraction common to all traces).
- Fixes worth ~0.5-0.9 m/s each: an inferred template, per-era S and
  per-era LSF-asymmetry calibration. None reaches the remaining ~1.4.

**The formal errors are not photon errors.** They are ~2.2x the photon
errors, inflated by the per-trace misfit (noise-only: 0.90 m/s nightly;
with the misfit: 1.78). "Photon-limited within a night" in earlier entries
means at the level of these inflated errors; the true photon floor for tau
Cet is ~0.5 m/s nightly. The model misfit (chi2_r ~4.5 per trace) is itself
a target.

## 2026-11-25: Timing correction re-validated per star and era (testbed branch overfit)

Under the evaluation protocol (DESIGN.md): v5 residuals without timing
regressed on each timing variant's predicted shift, per star and era, with
a per-night random term (slope 1 = correction right, 0 = noise).

| dv_best slope | 2016 | 2017 | 2018-19 | 2020+ |
|---|---|---|---|---|
| tau Cet | 0.10 +- 0.27 | 0.63 +- 0.21 | 1.01 +- 0.12 | 0.97 +- 0.24 |
| sigma Dra | 0.69 +- 0.29 | -1.79 +- 0.58 (32 exp) | 1.10 +- 0.26 | - |
| HD 122064 | 0.13 +- 0.15 | 0.52 +- 0.29 | 1.03 +- 0.89 | - |

Pooled before / from 2018: tau Cet 0.47 +- 0.17 / 0.93 +- 0.10; sigma Dra
0.04 +- 0.25 / 1.08 +- 0.26; HD 122064 0.27 +- 0.14 / 1.04 +- 0.60.

- **The timing term is real from 2018 on** (slope ~1 for every star) and
  survives on a held-out half of tau Cet nights (-0.77 [-1.26, -0.13] m/s
  ML excess). In 2018-20 it accounts for ~2.3 m/s in quadrature of tau
  Cet's unweighted nightly rms and ~1.8 m/s of its ML excess. The
  autofocus-gap term is under-predicted there (slope 1.9-2.9).
- **Before 2018 it is not validated**: right sign, 0.1-0.6 of the
  predicted size, and it makes HD 122064 worse (+0.58 [+0.26, +0.94]). The
  exposure meter was alive throughout and dv_best is effectively the FAU
  flux x guide-coupling model in every era (r = 0.95-1.00 with the meter
  version), so the meter is not what changed. What changed at the 2018-12
  site trip was the guide system (new cameras and plate scale, refocused
  FAUs; before it the FAU images were broad and T2/T4 not focused at the
  fibre). Hypothesis (untested): before the trip the FAU flux did not track
  the light entering the fibre.
- **Applied only from 2018**, tau Cet's ML excess is 1.89 [1.72, 2.08]
  (original) / 1.83 [1.66, 2.01] (x04) m/s, against 1.75 / 1.81 with timing
  everywhere and 2.39 / 2.44 with none. HD 122064 improves 3.16 -> 2.61.
  Rule adopted: timing from 2018 only; the pre-2018 flux record must be
  re-modelled before use, not scaled by a fitted slope.
- 51 Peg could not be tested (no timing rows).

This supersedes the "autofocus inside exposures in 2016-20" attribution in
the timing entry: it holds for 2018-20 only.

## 2026-11-25: Original vs x2-0.4, and how much of the chain is tuned to noise (testbed branch overfit)

Question (JDE): the test bed's v5 chain scored best on the original
extraction and worse on the nominally better x2-0.4. Real (copy what was
better) or spurious (find how we fooled ourselves)?

**Paired differences** (x04 minus original, same exposures, night-block
bootstrap, 95% CI; ML nightly excess):
- tau Cet: +0.06 [-0.08, +0.19]; nightly rms +0.11 [-0.39, +0.69];
  within-night +0.22 [-0.35, +0.80]. **No difference.** The earlier
  "2.47 vs 3.04 within-night" compared two separate CIs on a 92-exposure
  subset.
- sigma Dra +0.44 [+0.25, +0.62]; HD 122064 +0.77 [+0.33, +1.23]. **Real,
  and all in 2016** (sigma Dra 2016 +0.95 [+0.67, +1.25]; 2017-19 equal or
  better on x04; post-2018 sigma Dra x04 better by 0.20). In 2016 x2-0.4
  uses the 2018-19 pixel-flat stack (x04 uses stacked flats in every era;
  2016 is the only era whose stack comes from another epoch). The 2016
  differences persist for weeks within a star, partly track BERV, and are
  not shared between stars on the same night: a flat-field or
  wavelength-solution signature, not the chain (inferred; re-extraction
  test pending).
- Nothing flips along the chain: the difference is set before any v5
  step. What flipped was the metric. Unweighted nightly rms favours x04
  (it rescues faint frames); weighted rms and ML excess favour the
  original (2016 bright frames). The extraction comparison and the
  three-way comparison used different metrics and were both right.
- x04 keeps more faint traces (median 64 vs 46 per exposure) whose
  residuals are 1.15-1.31x their errors; with identical traces HD 122064's
  deficit falls from +0.82 to +0.35.

**Tuning and optimism.** About 200 looks at the residuals went into the
chain, almost all on the original extraction and scored on tau Cet's
unweighted nightly rms. With a fast stand-in for the chain (matches it to
0.01-0.05 m/s on tau Cet), a menu of 14 breaks, 4 exclusions and 240
regressions, and greedy selection:
- **Cross-validation** (20 random night halves): in nightly rms, 60-75% of
  the in-sample gain is optimism (tau Cet +0.45 in sample, +0.12 out). In
  ML excess optimism is small (+0.40 vs +0.33). The actual v5 knob set,
  frozen, shows about zero optimism (+0.37 in, +0.33 out) and helps x04
  equally: it was not tuned to the original's noise.
- **Null test** (40 noise-only realisations with the real times,
  telescopes, errors and covariates): the same search adopts all 12
  allowed knobs every time and "improves" nightly rms by 0.10-0.15 m/s
  (95th percentile 0.34), ML excess by 0.00-0.03 (<= 0.07). So
  nightly-rms gains of 0.1-0.2 m/s from a search are not evidence; ML
  excess is a much more honest metric.
- **Held-out stars, step by step:** the breaks help only tau Cet (-0.30);
  exclusions and the T2 count slope do about nothing. **Timing helps tau
  Cet (-0.69) but hurts HD 122064** (+0.58 [+0.28, +0.94] original, +0.35
  x04), all pre-2018. The RV residuals regressed on the timing correction
  give a slope of ~0 for every star pre-2018 (tau Cet 0.51 +- 0.58, sigma
  Dra -0.51 +- 0.89, HD 122064 0.06 +- 0.63) but 0.92 +- 0.32 for tau Cet
  post-2018. The pre-2018 timing corrections are not supported by the RVs.
  51 Peg K is unchanged by every step.

**How we fooled ourselves:** (1) compared two separate CIs on different
exposure sets; (2) compared results scored with different metrics; (3)
scored chain choices on a metric that a pure-noise search improves by
~0.15 m/s; (4) accepted timing on tau Cet and reported "no significant
change" elsewhere, although it degrades HD 122064.

Consequences: the tau Cet excess of ~1.75-1.8 m/s stands (it is in ML
excess, which barely responds to tuning, and NEID independently rules out
the star). The timing term's attribution (FINDINGS "timing") needs
re-validation per star and era. The evaluation protocol is now in
DESIGN.md.

## 2026-11-25: Three-way comparison and the tau Cet budget on x2-0.4 (testbed branch threeway)

Legacy production pipeline vs the test bed's v5 chain on the original
extraction (fit_v5, reproduced bit-exactly) vs the same chain on x2-0.4
(timing dv_best, T2 count-slope regression, kiwispec.yaml per-telescope
breaks, CTI, era zero-points). Legacy RVs are time-stamped with the UTC
JD of the header midpoint (not BJD); legacy covers 2016-02..2019-01.

tau Cet, 153 exposures common to all three; nightly rms / within-night /
ML nightly excess, m/s:

| Period (exp / nights) | Legacy | v5, original | v5, x2-0.4 + CTI |
|---|---|---|---|
| 2016-17 (60 / 44) | 16.3 / 9.7 / 14.7 | 3.95 / 2.57 / 2.47 | 4.95 / 2.18 / 2.28 |
| 2018-07..2019-01 (92 / 59) | 5.03 / 8.85 / 4.15 | 2.26 / 2.47 / 1.53 | 2.39 / 3.04 / 1.66 |
| overall (153 / 104) | 11.6 / 9.1 / 9.2 | 3.16 / 2.50 / 1.83 | 3.75 / 2.79 / 1.85 |

Legacy's scatter is uncorrelated with the test bed's (r <= 0.2) and is not
photons (formal errors are similar): the 3-4x gain is the pipeline.

**tau Cet budget on x2-0.4 + CTI** (all 352 exposures 2016-2026):
- ML nightly excess **1.78 [1.62, 1.96] m/s** (original extraction 1.75):
  the extraction is not the limiting term.
- Within-night: photon-limited (excess 0.00, < 0.28 m/s).
- Common to all four telescopes: the per-telescope part is < 0.62 m/s
  (95%).
- **Not BERV or season**: r(nightly residual, BERV) = +0.08; removing a
  BERV slope and an annual sinusoid leaves 1.77. (The BERV/season
  dependence seen in the per-exposure LSF kernels of lsfillum is absorbed
  there, not left in the v5 residuals.)
- Photon floor 1.48 m/s per four-telescope exposure, 1.05 m/s nightly;
  only 15% of exposures have all four telescopes.

**Per-era B-star LSF maps (Be0) in the full chain:** worse for tau Cet
(excess 1.78 -> 2.08), neutral for HD 122064, slightly worse for sigma Dra
(3.07 -> 3.46). lsfillum's gain (4.92 -> 4.77) was on the uncorrected QD
baseline and does not survive the v5 corrections.

Other stars on x2-0.4: sigma Dra nightly 10.94 -> 8.68 and HD 122064 8.58
-> 6.83 (smaller era steps, cleaner faint frames), but their ML excess
rises on common exposures (2.67 -> 3.07; 3.13 -> 3.85). 51 Peg K = 55.34
+- 1.28 (rms 3.19). CTI is a 0.2 m/s effect.

**Count floor:** removing the RV code's 150-count floor lets dark or
unfed fibres into the fit (median error 2.6 -> 7.8 m/s). A floor of 100 e-
per exposure-telescope recovers all 21 lost HD 122064 frames and leaves
the weighted result unchanged; specfast should keep a per-telescope count
floor near that level.

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
- **Not tellurics either (per-order test).** NEID's per-order CCF RVs
  (L2 CCFRVnnn) were fitted for a within-season trend (per-season offsets)
  and compared with each order's telluric content from NEID's own telluric
  model. The 55 telluric-free orders (< 2% of pixels below T = 0.999,
  mostly < 520 nm) carry the trend (weighted mean +0.53 +- 0.20 m/s per
  140 days); the 22 telluric orders do not (-0.05 +- 0.47); the per-order
  slope anticorrelates with telluric pixel fraction (r = -0.44). The
  trend repeats in both full seasons (NEID CCFRVMOD +1.13 and +1.25 m/s
  per season in 2023B and 2024B; specfast +0.08 and +0.28 on the same
  exposures; 2025B spans only 43 days). So it depends on the RV method
  (CCF with NEID's mask vs a template fit to the data) on the same L1
  spectra, not on the star, the barycentric correction or tellurics.
  Candidates still open: CCF mask and line-blend mismatch, CCF order
  weights, and detector-frame errors (wavelength solution, pixel
  structure), which move across the stellar lines as BERV changes.
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
