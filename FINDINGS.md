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

## 2026-11-22: Fibre feed (JDE) and what it implies

Each telescope feeds an octagonal fibre butt-coupled to a circular fibre.
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
