# specfast: architecture (draft 1, 2026-11-23)

Status: the skeleton is being built (2026-11-23). The test bed for experiments is Charlie's code; this repository is the
replacement. Regression targets come from reproducing Charlie's code:
51 Peg K = 54.0 +/- 1.9 m/s (DSST); HD 122064 2.3 m/s per-exposure RMS
in the Wilson+19 window (3 telescopes).

## Goals

1. Precise relative RVs from KiwiSpec iodine-in spectra, with honest
   error bars, across the whole 2015-2026 baseline (eras included).
2. Two stellar-template modes: an external template (DSST) and a
   template inferred from the star+iodine spectra alone (iShell style).
   A synthetic (Korg) template is the third mode and the bridge to
   stellar characterization.
3. Room to grow without rewrites:
   - wavelength solution and LSF predicted from the KiwiSpec optical
     design with fitted perturbations, shared across orders and fibres;
   - tellurics modelled, not only masked;
   - line-by-line velocities, so activity and spot confounders can be
     masked or modelled downstream;
   - a stellar-spectrum component in EXOZIPPy.
4. Out of scope: daytime-sky solar analysis (JDE). Any recheck of
   Charlie's daytime results is a one-off in the test bed, not a
   specfast feature.
5. Eventually G-CLEF, on Magellan and then GMT (JDE 2026-11-23). KiwiSpec
   is the first instrument, not the only one. We write both the
   extraction and the Doppler code for G-CLEF. Its differences:
   - no gas cell: simultaneous laser comb, etalon or ThAr, with the source
     chosen per fibre and per run (configuration, not instrument
     description); or early/late-night calibration for low precision. On
     GMT it rides two calibration fibres on the slit; on Magellan it is
     injected at the front end into the science/sky fibre pairs, so the
     sky fibre carries it (EPRV5 2023 poster);
   - two detectors split by a dichroic at ~540 nm; the 2021-12 optical
     design (the authority, JDE) covers 347-967 nm, not the ~1100 nm once
     quoted;
   - several observing modes, each its own fibre set: GMT PRV (seven
     pupil slices, one per mirror), NS-PRV, MR and HT; Magellan MR and HR
     (one science + one sky fibre), a 4-slice extreme-HR mode, and
     MagAO-X (one fibre, or a 16-spaxel IFU);
   - optical model: the G-CLEF Zemax/PyEchelle design
     (collaboration-private; never in this repo).

   So the instrument description (arms, detectors, orders, fibres and
   slices), the wavelength reference (iodine forward model, or drift from a
   simultaneous reference) and the LSF source (B stars, or calibration
   lines each exposure) must be pluggable, not built into the core.
6. No silent failures, no hidden global state, no environment variables
   that change the science; every product records its provenance.

## Two stages, one repository (JDE 2026-11-23)

specfast holds both the extraction and the Doppler code, as two stages
that meet only at a documented on-disk product:

    raw frames --[extract]--> ExtractedSpectrum --[doppler]--> velocities
                    ^                                  ^
                    +-------- Instrument description --+

- **Instrument description** (shared, data not code): arms (each with a
  detector and its order range), channels (a telescope fibre, a pupil
  slice, or a calibration fibre: comb, etalon, ThAr, sky), traces
  (channel x order), detector geometry, gain and read noise, and era
  breaks, and observing modes. KiwiSpec: one arm, four telescope
  channels, no modes. G-CLEF: two arms (blue/red, dichroic) and several
  modes. A mode names the channels that carry light, its fibre core,
  shape and field, its quoted resolving power and, per arm, its design
  resolving power, slit pitch and fibre-row offset along the dispersion.
  Channels are logical (S0 is the first science fibre of whichever mode
  is in use); a run selects the mode (`mode` in the run config, or the
  instrument's `default_mode`; Magellan has none, so a run must choose). Optical-model parameters are calibration products, not part
  of the public description when they derive from private design files.
  `specfast-zemax2instrument` (`specfast.optics`) derives the public facts
  (orders and their wavelength ranges per arm, detector format, resolving
  power, order spacing, slit pitch, and per mode its resolving power,
  pitch and row offset) from a Zemax design by ray tracing;
  everything else comes from an overrides file. The G-CLEF descriptions
  were made this way from the 2021-12 design.
- **Stage 1, extract**: raw frame plus calibration products (stacked bias,
  profiles, traces, scattered light, optional stacked flat) to an
  ExtractedSpectrum. Reference channels are extracted like any other.
- **ExtractedSpectrum** (the contract): per arm, arrays over
  (channel, order, pixel) of flux, variance and a bitmask; per-trace
  diagnostics (cross-dispersion width and centroid, profile chi2, halo);
  a normalized header (times, target, barycentric inputs, environment);
  optional wavelength per (channel, order, pixel) with its source; and
  provenance. One multi-extension FITS file per exposure. Either stage
  can be replaced: the Doppler stage can run on another pipeline's
  extraction if it is converted to this product.
- **Stage 2, doppler**: forward model and fit (below), then combination.
  The wavelength reference is a component: an iodine cell inside the
  forward model (KiwiSpec), or a simultaneous reference whose drift is
  measured from the reference channels and applied to a calibration-lamp
  solution (G-CLEF). The LSF source is likewise pluggable: B-star frames
  (KiwiSpec) or calibration lines in the same exposure (G-CLEF).
- Package layout: `specfast.instrument`, `specfast.products`,
  `specfast.extract`, `specfast.doppler`, `specfast.combine`, plus shared
  `conventions`, `config` and `provenance` modules.

## The forward model

For one exposure e, fibre (telescope) f, order o, at detector pixel x:

    F(x) = C(x) * Pixel[ LSF(x) (x) ( S(lam * D_e) * I2(lam) * T_e(lam) ) ](x)

- `lam(x)`: the wavelength solution;
- `S`: stellar spectrum, Doppler factor `D_e = 1 / (1 + v_e/c)`
  (relativistic composition with the barycentric correction);
- `I2`: iodine cell transmission, with a strength scaling the optical
  depth, `I2 = exp(-k * tau_FTS)`;
- `T_e`: telluric transmission (observed frame);
- `(x)`: convolution with an LSF that can vary with x;
- `Pixel[...]`: integration over the pixel, not point sampling;
- `C`: continuum and blaze.

The model is evaluated on a fine uniform grid in ln(lambda), convolved,
then integrated onto pixels. Without a gas cell (G-CLEF) `I2 = 1`, and
`lam(x)` is the calibration solution shifted by the drift measured from
the simultaneous reference channels.

## Components

Each factor is a component behind one small interface. A component:

- declares its parameters, and for each one its **scope**: global,
  per era, per night, per exposure, per fibre, per order, per order
  segment, or a product of these (e.g. fibre x order);
- declares the **frame** it lives in: detector pixel, observed
  wavelength, barycentric or stellar rest frame;
- evaluates as a **pure function** of (parameter arrays, static data);
  it does no I/O and holds no mutable state;
- is written against plain array operations (no scipy interp1d inside
  the model), so the same code can later run under JAX or PyTensor for
  gradients. NumPy is the first backend.

| Component | First implementation | Later implementations |
|---|---|---|
| Wavelength | polynomial in pixel, per (exposure, fibre, order); degree configurable (default > 2) | optical model: grating equation plus a camera/distortion map derived from the Zemax design, with a few low-order perturbation terms shared by all orders and fibres, per exposure or night |
| LSF | Gaussian, sigma per (fibre, order) frozen from the B-star calibration, constant in km/s (a static along-order width gradient was tested 2026-11-22 and gains nothing; see FINDINGS) | Gauss-Hermite or sum of Gaussians; shape from the optical model times a fitted perturbation |
| Iodine | NIST 2018-08 FTS scan (exact vacuum, native wavenumber grid; 4950-6450 A), optical-depth strength. Never I2_0.1 uncorrected (+/-300 m/s air-dispersion error) | per-era atlas, cell temperature term; optional learned observer-frame correction (halves chi2, no RV gain so far) |
| Telluric | static mask from the atlas at T < 0.98-0.99 (threshold barely matters); orders 18-20 (590 nm water band) masked harder or down-weighted; per-exposure spectral water column saved as a diagnostic | fitted H2O columns from a line-by-line model (TAPAS / molecfit style) with its own line shapes; an atlas raised to a power fails (atlas noise, and one column can't fit the water band) |
| Star | DSST template; inferred template | Korg synthetic spectrum from (Teff, logg, abundances, vsini, macroturbulence) |
| Continuum | blaze function times a spline or higher-order term able to follow 10-20 A structure (a quadratic leaves ~1% rms) | per-era learned shape |
| Masks / weights | telluric, sky emission ([O I] 5577), bad pixels, template artefacts | stellar-line masks chosen by activity sensitivity |

Masks and weights compose as per-pixel layers, each defined in its own
frame (tellurics in the observed frame, stellar lines in the stellar rest
frame) and mapped to pixels for every exposure.

## Fitting

- **Problem assembly**: a configuration names the components, which
  parameters are free, and how they are shared across blocks. The
  engine builds one parameter vector and a block-sparse Jacobian.
- **Velocity granularity**: the wavelength solution and LSF are
  per order (or shared across orders later), but velocities are fitted
  per segment of an order, and per line if asked. The review found
  ~113 m/s of static structure between segments of one order that a
  single whole-order velocity cannot absorb; segments sharing one
  wavelength solution keep the whole-order stability.
- **Solver**: bounded nonlinear least squares, per order in parallel at
  first. When parameters are shared across orders (the optical model),
  the engine solves the shared block and the per-order blocks
  alternately, or jointly with the sparse Jacobian.
- **Outputs per exposure**: every segment velocity with its covariance,
  the fitted nuisance parameters, residuals and quality flags. Nothing
  is discarded at this stage; the combination stage decides.

## Templates

- **DSST**: load, validate, record provenance.
- **Inferred**: the template is a free spectrum on a fine grid, fitted
  jointly across many iodine-in exposures whose barycentric velocities
  differ, with regularization; iterate template and RVs. Exposures
  without iodine (where they exist) are a stronger prior. This is the
  mode for TOIs without a DSST template.
- **Synthetic (Korg)**: a precomputed grid or emulator for speed; Korg
  itself is Julia, called out of process, never inside the fit loop.

## Combination

- Joint solve of the per-segment velocities: v = RV_e + O_(group, era),
  with error model sigma^2 = beta^2 sigma_i^2 + s^2 (beta < 1 allowed),
  offsets marginalized and their uncertainty propagated into the RV
  covariance. A known signal (an orbit) can be solved jointly.
- Era breaks are configuration, with defaults from the instrument log.
- Line-by-line and activity indicators are computed here from stored
  segment or line velocities, without refitting spectra.

## Data model and provenance

- **Exposure**: a normalized view of one reduced KiwiSpec frame. A
  header layer maps every era's keywords to one schema (target
  coordinates, which changed from TARGRA1 to TARGRAT1 in 2018; times;
  iodine state; fibre-to-telescope map; pressures and temperatures).
- **Calibration products** (iodine atlas, LSF map, instrument model,
  telluric model, masks) are versioned files with content hashes.
- Every output records the code version, the full configuration and the
  calibration hashes. Every failure is logged with the file, stage and
  exception; nothing is skipped silently.
- Configuration is an explicit YAML file per run.

## Testing

- Injection-recovery on synthetic spectra made by the forward model
  itself: known RVs, offsets, LSF and wavelength perturbations.
- Regression targets on real data: 51 Peg K, HD 122064 RMS in the
  Wilson window and on the full baseline.
- Unit tests for every component (normalization, Doppler sign,
  convolution width, pixel integration).

## EXOZIPPy

What it changes here: four cheap choices that would be expensive to
retrofit.

1. Components are pure functions over plain arrays, so the stellar,
   LSF and instrument pieces can be re-expressed as PyTensor graphs
   (EXOZIPPy samples with PyMC) without changing their meaning.
2. The Star component's synthetic mode takes physical parameters (Teff,
   logg, [X/H], vsini, RV) through the same interface EXOZIPPy would
   sample.
3. Conventions match EXOZIPPy: m/s, BJD_TDB, the barycentric sign, the
   relativistic velocity composition.
4. The instrument calibration (wavelength, LSF, iodine strength per
   exposure) is a saved product, so a consumer can evaluate the model
   for any exposure without rerunning the extraction.

What stays in EXOZIPPy: the sampler integration, priors, ties to the
SED, isochrones and orbits, how a Korg grid is interpolated inside a
PyTensor graph, and which spectra to include.

What does not move to EXOZIPPy: precise RV extraction. It has
thousands of nuisance parameters per exposure and is a point-estimate
problem; EXOZIPPy keeps consuming RVs. The spectrum component would
fit stellar parameters to a coadded or inferred template, or a few
high-S/N exposures, with the instrument calibration held fixed.

## KiwiSpec optical model (first results, 2026-11-20)

Reconstructed from the instrument's optical design and the SPIE papers.
The design files, code and write-up are collaboration-private and stay
out of this repo.

- 7 physical constants per hardware era (camera focal length, one
  distortion term, detector rotation, fibre-line angle, echelle gamma
  and blaze-angle offsets, position) match iodine-anchored wavelength
  solutions to 0.04-0.05 px rms in both the 2016 and 2017+ setups.
- A static per-(fibre, order) residual of ~0.03 px (~30 m/s) remains,
  repeatable over months: a calibration table, not free parameters.
- Per exposure, x0 alone fits the wavelength solutions themselves, but
  not well enough for RVs (see below).
- Fibre-to-fibre offsets are predicted to 0.02-0.04 px.
- LSF: the design predicts the shape along an order (narrower in km/s,
  broader in pixels toward the red) but not the absolute width or its
  order/fibre dependence; those stay empirical (B stars). The measured
  along-order width gradient (+/-3-5% at the ends) is static and costs
  ~0.3 m/s rms of BC-dependent error if ignored, so it is optional; if an
  LSF term is added per exposure, it should be h3, not width or gradient.

Inside the RV fit (wavelength ladder on HD 122064 2016-2020 and 51 Peg,
2026-11-20), the rigid form (per-exposure x0 only) failed. The static
per-trace table is stable to only ~0.015 px (~15-22 m/s per order) over
years: RMS 12.8 vs 10.1 m/s, and errors underestimated by ~30%. Sharing x0
across fibres is worse still. What works: per-order offset plus slope on top
of the optical model (RMS 9.7, sqrt(chi2_r) 1.60), or a free quartic (9.4,
1.51), against 10.1 / 1.68 for the free quadratic. The optical model's clear
payoff is the starting guess. It rescues 23 Dec 2016 - Mar 2017 exposures
where the stored pipeline wavelengths send the quadratic fit to wrong
minima.

Wavelength component, production form:
  lambda(x; fibre, order, exposure) = optics(theta_era, x) + D_era(x)
      + a0(fibre, order, exposure) + a1(fibre, order, exposure) * x
      [+ higher free terms if the ladder keeps favouring them]

- No detector stitching was found. Steps at 512-px boundaries are below
  ~0.02 px, from a stack of 127 + 322 star, 106 B-star and 72 sky frames
  across two eras.
- The missing term instead is a smooth along-order distortion D(x),
  +/-0.1 px (~70-100 m/s), quasi-periodic at ~800 px.
- D(x) is identical across orders, fibres and datasets within an era
  (correlation 0.92-0.98). It moves with the spectrum, not the detector
  (best cross-era match at the ~68 px remount shift), so it is optical.
- D(x) is a per-era calibration product. A detector map stays possible
  if better data (a comb) ever demands it.

## Stage 1: extraction

Cross-talk is not a driver: measured leakage is <= 1e-3, worth under
0.2 m/s. Requirements:

- Fit all traces in a column simultaneously, with an empirical profile
  per trace from fibre flats.
- Model the scattered light with a 2D or local background. The pedestal
  is 0.5-1.4% of the trace flux and 3x larger in the blue.
- Never zero out low-flux windows; report dark traces.
- No hard count floor anywhere downstream: faint traces enter with honest
  errors and the fit down-weights them (the legacy 150-count floor
  silently dropped 11 usable frames).
- Re-centre the traces per exposure.
- Output, per (exposure, fibre), the cross-dispersion width and
  centroid, and a residual map, as illumination diagnostics.

Pilot results (extract2, 2026-11-22) settle the recipe:
- profiles: empirical per trace, from fibre flats where they exist (only
  2016-01 and 2016-11), otherwise stacked bright frames; pick the source
  per era by held-out chi2;
- the 2D scattered-light model and per-trace re-centring are both
  essential for per-telescope stability;
- calibrations: a long-term stacked bias (or overscan only), not a
  nightly 3-frame master, which adds ~3.5 e- of pixel noise; **no darks**;
  **no nightly slit flats**;
  optionally a multi-night stacked pixel-to-pixel flat for bright and
  daytime frames;
- extraction alone gives < 1 m/s for bright stars; its value is faint
  frames, daytime frames and robustness (no crashes, no lost frames).

Frame selection (robofast headers, 2026-11-23): skip any frame with
`SIMULATE = T` or `IMAGETYP = test` (robofast marks dry-run frames this
way from 2026-11-22; their names also contain `.test`), and skip
non-FITS sidecars (robofast writes `<raw name>.json` next to each
spectrum). Earlier dry-run frames are unmarked, so the dated exclusion
window in `kiwispec.yaml` stays. robofast frames will also carry
per-telescope target coordinates, proper motion, epoch, parallax and RV
(`TARGRAn`, `PMRAn`, `TARGEPOn`, `PARLAXn`, `RVn`, ...) and `SPECPRES`;
"UNKNOWN" means absent. Use these for the barycentric correction when
present.

## Era breaks

Dated from the vacuum and thermometer logs and the frame headers
(instrument-log analysis, 2026-11-20). Default era starts: 2016-01-20,
2016-09-28, 2016-11-22, 2017-10-02 (Wilson+19), 2019-09-18, 2020-10-01,
2021-09-12, 2024-03-15, 2026-01-21; excluded windows 2017-04-25..10-01,
2019-10-01..10-21, 2020-09-05..09-30. Between 2021-09 and 2023-07 the
bench was not regulated: regress on bench temperature within the era.
Hardware history (site trips) is in HISTORY.md.
Per-telescope breaks (LSF width, offsets, throughput), not
spectrograph-wide, as tested on the data (telbreaks, 2026-11-23): only
2018-12-17 for T2 and T3 (the site trip: T3 recabled after a cable-wrap
failure, ZWO guide cameras replaced the SBIGs, FAUs refocused), each with an RV
offset; a static h3 offset there is plausible (T2 h3 +0.008) but untested.
The earlier guesses (T3 2018-07-01, 2018-12-22 for all four telescopes,
2019-09-18 per telescope) did not help or made things worse. Guiding
episodes are per-telescope exclusion windows, not eras: T2 2019-05-08..07-14
(excluding it improved sigma Dra).
The break list is configuration.

## Open questions

- Calibrate the optical model from B-star frames (the first fit used
  daytime sky) and test structure above quadratic within an order.
- G-CLEF blue orders (m ~175-165): the slit is longer than the order
  spacing, so the end traces of adjacent orders blend. The plan of record
  was to discard those orders; specfast's goal (not a requirement) is to
  model the blend by fitting neighbouring orders' end traces jointly.
- G-CLEF: pupil-slice traces are closely packed; does the joint
  all-traces-in-a-column fit carry over, or is a slice-combined profile
  needed? Reference-channel bleed into science traces (comb lines are
  bright) must be measured, not assumed negligible as on KiwiSpec.
