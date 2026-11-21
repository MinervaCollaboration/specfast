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
  polynomial background. Raw 2D frames: gateway /nas/kiwispec/nYYYYMMDD/.
- Results: `work/xtalk/`. Raw frames: `data/raw2d/`.

## 2026-11-21 Guiding and flux-weighted midpoints (branch fluxmid)

Data found on the gateway NAS:
- FAU guide images, `/nas/t{1-4}/nYYYYMMDD/*.FAU.*`, 2015-2026. 2,324 of
  the 2,451 (exposure, telescope) pairs are usable.
- Guide-loop logs, `/nas/log/<night>/control.log`: star and fibre
  position per guide frame.
- Exposure meter, `/nas/kiwilog/<night>/expmeter.dat`: 1 Hz, summed over
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

- In our copies and in the gateway's `/Data/kiwispec-proc`, 2016 to
  mid-2018 is still v0.1-v0.6: per-trace +/-5 px window fits that zero
  low-flux windows. Five versions in two years.
- v1.0.0 (joint fit of all traces in a column, plus background) was
  only ever run forward from mid-2018.
- Raw 2D frames for every night are on `/nas/kiwispec/`. A re-extraction
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
- Flux-weighted midpoint: look for exposure-meter logs.
- iota Per's missing 2016 jump.
- Recalibrate the optical model from B-star frames.
- Inferred-template mode; Korg prototype; specfast skeleton.

## 2026-11-21: The two iodine atlases differ by air dispersion

Both atlases are in the gateway's `~/minerva-pipeline/minerva_dopcode/templates/`:

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
