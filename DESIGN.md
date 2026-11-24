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
  optional wavelength per (channel, order, pixel) with its source;
  optionally, per trace, a sparse resolution matrix and flux covariance
  (spectro-perfectionism; see "Extraction modes"); and provenance. One multi-extension FITS file per exposure. Either stage
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

    F(x) = C(x) * R(x) * Pixel_dx[ LSF(x) (x) ( S(lam * D_e) * I2(lam) * T_e(lam) ) ](x)

- `lam(x)`: the wavelength solution;
- `S`: stellar spectrum, Doppler factor `D_e = 1 / (1 + v_e/c)`
  (relativistic composition with the barycentric correction);
- `I2`: iodine cell transmission, with a strength scaling the optical
  depth, `I2 = exp(-k * tau_FTS)`;
- `T_e`: telluric transmission (observed frame);
- `(x)`: convolution with an LSF that can vary with x;
- `Pixel_dx[...]`: integration over the pixel, not point sampling, with
  pixel edges displaced by the detector map dx(p);
- `R`: detector response residual left after flat-fielding;
- `C`: continuum and blaze.

Four frames (JDE 2026-11-24). Each component lives in exactly one:

| Frame | Moves with | Components |
|---|---|---|
| Star (stellar rest) | RV + barycentric correction | stellar template, stellar-line masks |
| Observatory (observed wavelength) | nothing: fixed in wavelength | iodine, tellurics, sky emission |
| Spectrograph optics | the spectrum, when the optics change (MINERVA: the ~68 px remount shift) | wavelength solution, along-order distortion D(p), LSF, blaze |
| Detector (pixel) | nothing: fixed to the silicon | pixel-position map dx(p), response residual R(p), stitching, charge-transfer effects, bad pixels |

The frames separate only through relative motion. The star crosses the
pixels as the barycentric velocity changes over a year (KiwiSpec: about
0.7-1 km/s per pixel, so tens of pixels); the observatory frame does not.
A static detector-frame error therefore imitates a barycentric-velocity
dependent template error, and a template inferred while ignoring the
detector absorbs it. Iodine and tellurics share a frame and separate only
through priors and airmass/water scaling. Optics and detector separate
through optical changes (remounts, drifts) and, on a comb instrument,
through comb lines sampling every pixel phase.

Optics parameters are not only per era (JDE 2026-11-24). Eras capture
discrete events (remounts, recabling, cleanings); between them the optics
follow the environment continuously: temperature (focus, flexure, grating
and glass), pressure (residual-gas index; matters during vacuum
outages), and the CCD and cell temperatures. So each optics-frame
parameter is era value + smooth function of per-exposure environment
covariates (bench/spectrograph temperatures, pressure, CCD temperature),
with the per-exposure free terms on top. Low-order wavelength drift is
absorbed by the per-exposure terms anyway; the environment model matters
for what they cannot absorb: LSF shape (thermal focus varies with field
position, unlike an illumination change) and the D(p) shape. Missing or
bad covariates (sensor dropouts, unregulated periods) must be flagged,
not filled.

The model is evaluated on a fine uniform grid in ln(lambda) (step about
0.05 km/s below 30 cm/s: a 0.25 km/s grid with the raw iodine scan
leaves 0.69 m/s; FINDINGS 2026-11-24, iodinfo), convolved,
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
| LSF | (with a resolution matrix in the product: apply it, no free LSF) Gaussian, sigma per (fibre, order) frozen from the B-star calibration, constant in km/s (a static along-order width gradient was tested 2026-11-22 and gains nothing; see FINDINGS) | Gauss-Hermite or sum of Gaussians; shape from the optical model times a fitted perturbation. Required for 1 m/s and below: a per-exposure h3 shared smoothly across orders (an unfitted h3 change of 0.01 is 17 m/s; fitting it costs 8-14% in sigma); static shape pooled over exposures to ~0.002 (30 cm/s) |
| Iodine | NIST 2018-08 FTS scan (exact vacuum, native wavenumber grid; 4950-6450 A), optical-depth strength. Never I2_0.1 uncorrected (+/-300 m/s air-dispersion error) | per-era atlas, cell temperature term; optional learned observer-frame correction (halves chi2, no RV gain so far) |
| Telluric | static mask from the atlas at T < 0.98-0.99 (threshold barely matters); orders 18-20 (590 nm water band) masked harder or down-weighted; per-exposure spectral water column saved as a diagnostic | fitted H2O columns from a line-by-line model (TAPAS / molecfit style) with its own line shapes; an atlas raised to a power fails (atlas noise, and one column can't fit the water band) |
| Star | DSST template; inferred template | Korg synthetic spectrum from (Teff, logg, abundances, vsini, macroturbulence) |
| Continuum | blaze function times a spline or higher-order term able to follow 10-20 A structure (a quadratic leaves ~1% rms) | per-era learned shape |
| Detector | none: flat-fielded, bad pixels masked; stitching steps < 0.02 px measured on KiwiSpec (FINDINGS 2026-11-20) | pixel-position map dx(p) and response residual R(p) per detector, from comb/etalon lines or flats, as a calibration product with an optional fitted perturbation |
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
- **Template zero-points are a template property.** Each DSST carries
  per-order (and per-segment) wavelength zero-point errors of 40-100 m/s,
  common to all telescopes and shared within a Keck template run
  (FINDINGS 2026-11-24). Fit one offset per (template, order[, segment]),
  shared by all fibres, and store it with the template, not the
  instrument; per-(fibre, order) offsets then only carry 5-17 m/s.
  Inferred templates remove these errors at the source and are the
  preferred mode; on a comb-calibrated instrument (G-CLEF) they are the
  only way to avoid per-order template offsets.

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

5. The released velocity product is a raw redshift (next section), so
   the barycentric correction is part of EXOZIPPy's fit.

### Raw redshifts: the barycentric correction lives downstream (JDE 2026-11-24)

specfast releases the raw measured redshift `c * z_meas`, `z_meas =
lambda_obs / lambda_ref - 1`, with no barycentric correction applied, in
the standard EXOZIPPy reads (`data_format: raw_redshift`; EXOZIPPy
`docs/raw_redshift_data.md` and `components/rvinstrument/rvinstrument.md`).
EXOZIPPy then predicts the observed redshift from the FITTED star
(position, proper motion, parallax, systemic RV at a stated epoch,
refit jointly with Gaia epoch astrometry rather than frozen at catalogue
values), the orbits, the observer and the exposure: multiplicative cross
terms, perspective acceleration, the companion's light-travel time and
gravitational redshift, and the exposure average are all in the model.
This is how the ~1 mm/s barycentric target is met.

What that requires of specfast:

- The Doppler fit's velocity parameter is the TOTAL observed redshift of
  each exposure relative to the template (`1 + z_meas = (1 + z_B)(1 +
  z_star)`, never split). A provisional catalogue barycentric velocity is
  used only to place exposures in the star frame for template inference
  and for the separability diagnostics; it never enters `z_meas`.
  Report `c z`, not `c ln(1 + z)` (they differ by 1.5 m/s at 30 km/s).
- Per exposure (per telescope channel for KiwiSpec): `c z_meas` and its
  uncertainty (and the per-order/segment values with covariance); the
  flux-weighted midpoint with its time scale and frame (JD_UTC at the
  observatory); the observatory location; the exposure-meter record
  (side file, bins as short as the meter allows), else the exposure
  time; the template/zero-point definition (relative within the
  instrument unless the template is absolutely calibrated); every
  correction applied to `z_meas` (drift, charge transfer, telluric
  treatment, zero points) and confirmation that no barycentric term is.
- Chromatic exposure weighting: the photon-weighted time differs by
  order (seeing, atmospheric dispersion). Release per-order redshifts with
  per-order meter records where the meter is chromatic (G-CLEF); this
  needs a per-order (chromatic) exposure-meter input on EXOZIPPy's side.
- Optionally, for audit only: the provisional barycentric velocity and
  the star model it used, and a corrected velocity for quick looks.

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
      [+ a2 x^2; in practice a quadratic in x' = (x + D(x)) / x_med]

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
- Fixing D(x) cuts the spectral chi2_r by 2-5% (4-5x the quartic's gain)
  and leaves the RVs unchanged; the quartic gains nothing once D is in
  and can hurt. So: quadratic per (exposure, fibre, order), no quartic
  (FINDINGS 2026-11-24, wavedist).

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

### Extraction modes (JDE 2026-11-24)

At 1 m/s the 1D recipe above suffices. At 10 cm/s the extracted
spectrum's line-spread function itself depends on the extraction
(weights, illumination, flux) wherever the 2D PSF does not separate into
a cross-dispersion profile times a spectrum: tilted or curved fibre
images, a PSF varying over the detector, G-CLEF's seven adjacent pupil
slices with overlapping wings. Three modes, sharing one calibration
product, a 2D PSF model per (channel, arm) measured from comb/etalon and
flat frames and interpolated with the optical model:

1. **1D profile fitting** (current; KiwiSpec): simultaneous fit of all
   traces in a column with empirical cross-dispersion profiles. The
   Doppler stage fits its own LSF.
2. **Spectro-perfectionism** (Bolton & Schlegel 2010): solve for the
   spectra of all traces jointly through the 2D PSF, then reconvolve to a
   well-conditioned resolution matrix R. The product carries R and the
   flux covariance per trace; the Doppler stage applies R instead of
   fitting an LSF.
3. **Full 2D forward model**: no extraction product for science; the
   Doppler stage evaluates its model through the 2D PSF onto the raw
   pixels (with the detector frame: dx(p), R(p), charge-transfer terms)
   and fits the image. Stage 1 then reduces to calibration (bias,
   scattered light, PSF, traces). Most exact, most expensive.

Which mode G-CLEF needs was decided by simulation (FINDINGS 2026-11-24,
G-CLEF extraction modes): noise-free frames ray-traced from the G-CLEF
optical design (collaboration-private) with star, comb and flats.

- **Mode 1 is the production mode**, with two requirements:
  - extraction weights fixed from a reference model, never recomputed
    per exposure, since per-frame weights make the LSF depend on flux;
  - comb light subtracted as a 2D model, scaled by the comb flux, before
    extracting the science slices (or an empty slot between comb and
    science fibres).

  With both, slice-flux changes and comb or star flux changes leave
  <~1 cm/s. Mode 1 is also the most robust to trace offsets across the
  dispersion.
- **Mode 2** only helps for comb leakage, and only with the resolution
  matrix computed per fibre. It is about 90x more sensitive than mode 1
  to cross-dispersion trace errors and costs ~1.5 core-hours per arm per
  exposure.
- **Mode 3 is not needed.** It is exact only with a perfect PSF and is
  the most sensitive to trace offsets.
- **The budget is dominated by illumination inside the fibre, which no
  extraction removes.** A 1% near-field gradient along the dispersion is
  ~6 m/s, so the near-field centroid must be stable to ~2e-5 of the core
  for 10 cm/s: a scrambling and pupil-stability requirement on the
  instrument, and on the comb fibre's own near field.

KiwiSpec's real data are the wrong test bed for this: its other error
terms (5-11 m/s nightly) hide the differences.

Frame selection (robofast headers, 2026-11-23): skip any frame with
`SIMULATE = T` or `IMAGETYP = test` (robofast marks dry-run frames this
way from 2026-11-22; their names also contain `.test`), and skip
non-FITS sidecars (robofast writes `<raw name>.json` next to each
spectrum). Earlier dry-run frames are unmarked, so the dated exclusion
window in `kiwispec.yaml` stays. robofast frames will also carry
per-telescope target coordinates, proper motion, epoch, parallax and RV
(`TARGRAn`, `PMRAn`, `TARGEPOn`, `PARLAXn`, `RVn`, ...) and `SPECPRES`;
"UNKNOWN" means absent. These header values (Gaia DR2-era catalogue
astrometry) are provisional: use them only for frame bookkeeping and for
an audit-only corrected velocity, never for the released redshift (see
"Raw redshifts: the barycentric correction lives downstream").

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

## Error budget toward 10 cm/s (G-CLEF)

G-CLEF's published PRV error budget (Podgorski et al. 2014, SPIE 9147,
91478W; concept-design stage) sets a single-measurement instrument
requirement of 40-50 cm/s with a goal of 20 cm/s; 10 cm/s is the
precision expected for a series of measurements on a quiet star. 10 cm/s
is therefore the total, and no single term may use it (JDE 2026-11-24).
Its top level (37 cm/s RSS): post-calibration residual 33 (calibration
source accuracy, 5 for a comb or etalon, 30 for ThAr, plus 10% of the
calibratable instrument errors: internal pressure 4, mechanical 10,
thermo-elastic 24, CCD block stitching 3), barycentric correction 2,
non-calibratable instrument errors 14 (stray light 5, detector 10,
micro-vibration 5, software fitting 6), external non-calibratable errors
10 (guiding 8, assuming scrambling gain 10^4; focus 3; ADC 5).

NEID's error budget (Halverson et al. 2016, SPIE 9908; arXiv:1607.05634)
is the more modern reference: 27 cm/s instrumental total. Its software
and analysis terms are large: reduction pipeline 10, calibration-process
software 10, micro-tellurics 10, sky-fibre subtraction 10 cm/s; also
barycentric 1.7, charge-transfer inefficiency 5, readout thermal change 5,
stitching 3, pixel inhomogeneity 1, calibration source 5.7 (photon noise
4.0, stability 4.0), near-field scrambling 3.5, far-field scrambling 5.0,
stray light 5.0, modal noise 2.5 + 2.5.

**These budgets are requirements, not specfast's goal (JDE 2026-11-24).
specfast aims to be photon-limited**: every error that specfast introduces
or is responsible for modelling (numerical and model-mismatch error,
calibration-process software, tellurics, sky, barycentric correction,
detector corrections, template) must be shown, by injection on realistic
simulated data, to be small compared with the photon noise of the data it
is applied to. Operational criterion:

- per exposure: specfast-attributable systematic error <= 0.2 sigma_photon
  (adds <= 2% to the variance);
- for errors correlated between exposures (static, BERV-, season- or
  era-dependent), which do not average: <= 0.2 sigma_photon / sqrt(N),
  with N the exposures in the season or data set being combined.

Instrument terms that specfast cannot remove (fibre illumination, thermal
and mechanical motion) are modelled down to the photon limit where the
data constrain them (per-exposure illumination kernel, environment
covariates, simultaneous calibration) and otherwise reported, with their
budget allocations, as the instrument's floor. The published allocations
(G-CLEF above, NEID) are the ceiling a result must never exceed, not the
target.

The ~0.5-1 m/s floor of the best iodine programmes is treated as a
limit of their modelling, not of iodine (JDE 2026-11-24): independent
chunk-by-chunk LSFs fitted per exposure, deconvolved templates, scalar
iodine atlases, no shared optical model; development largely stopped
once stabilised spectrographs overtook it. Our own findings fit that
view: each limit we have hit so far (air dispersion in the atlas,
+/-300 m/s; the along-order distortion D(p); 40-100 m/s template
zero-points) was a modelling error, not a photon limit. What is
intrinsic to iodine is information, not a floor: the band is limited
(~500-620 nm), the cell absorbs light, and star, iodine and LSF must be
separated by the data (barycentric spread, ensemble pooling, priors
from B-star frames and the optical model). How far the modelling can go
is measured, not assumed: an information-content study (simulated
KiwiSpec star + iodine frames fitted with the full model family; the
Cramer-Rao bound, plus each model component's error sensitivity) gives
the attainable precision and ranks the modelling terms. Result
(FINDINGS 2026-11-24, iodinfo): ~1.1 m/s per trace at S/N 200 for a
Sun-like star with the LSF shared across orders and a per-exposure h3;
the legacy chunk LSF costs 30-45% in sigma; the floor comes from h3 and
template-depth errors. 10 cm/s needs at least six terms held to ~5
cm/s each, several by external calibration. Each term below is assigned a frame, the specfast
component that carries it, and where it can be tested. Sizes are
MINERVA measurements where we have them; the rest are to be quantified
(G-CLEF optical model, public comb-calibrated data, injection tests)
before they are trusted.

| Term | Frame | specfast component | MINERVA (measured) | Test bed |
|---|---|---|---|---|
| Template wavelength zero-points (DSST) | star | per-(template, order) offsets; inferred template | 40-100 m/s per order, static, absorbed by offsets | MINERVA; injection |
| Template noise and line errors that move with barycentric velocity | star | inferred template with its own covariance | template-specific ~0.75 m/s in exposure RVs; a larger template-independent BERV pattern (4-7 m/s per order, mostly cancelling) of open cause | MINERVA; injection |
| Stellar activity, granulation, oscillations | star | line-by-line velocities, activity-sensitive line selection, exposure strategy | not separated yet | public solar data |
| Micro-tellurics (lines < 1% deep) | observatory | modelled telluric component, per-exposure water and airmass | masked at 0.98 (too crude for 10 cm/s) | injection; public comb data |
| Sky emission, moonlight | observatory | sky component from sky fibres | [O I] 5577 masked | G-CLEF sky fibres |
| Iodine model (atlas, cell temperature, LSF-velocity degeneracy) | observatory | iodine atlas + learned correction, LSF shared through the optical model and pooled over exposures | atlas choice 0-5 m/s on order pattern; simulation: per-feature depths 1% -> 0.25 m/s, atlas noise 0.3% -> 0.18 m/s, cell temperature negligible | MINERVA; iodinfo simulation done |
| Barycentric correction (target ~1 mm/s; allocations of 1.7-2 cm/s are ceilings only) | star/observatory | not in specfast: specfast releases raw `c z_meas`, and EXOZIPPy fits the correction with the star's astrometry refit jointly with Gaia epoch astrometry (see "Raw redshifts"). specfast's part: total-redshift fitting, flux-weighted UTC midpoints to ~0.1-0.2 s, the exposure-meter record (per order where chromatic) | flux-weighted midpoint per exposure (fluxmid) | EXOZIPPy (agrees with barycorrpy to 0.12 mm/s, PINT to 0.02 mm/s); exposure-meter data |
| Wavelength solution and drift | optics | comb/etalon per exposure, D(p), quadratic per trace | D(p) 0.1 px, residual 0.015 px | G-CLEF design; public comb data |
| Comb line centres (side modes) | instrument (calibration source) | comb component: exact frequencies f0 + n K f_rep, plus a side-mode centroid shift per wavelength region from the source's own characterization (FTS), optionally a fitted perturbation; a per-exposure line-intensity envelope | n/a | allocation 5 cm/s (calibration source accuracy). Astro-comb papers (Li et al. 2012, SPIE 8446 84468X; Phillips et al. 2012, 84468O) put the side-mode shift at 1-10 cm/s, varying with the broadened spectrum's profile |
| Calibration-vs-science differential drift | optics | per-fibre drift model | n/a (iodine is in the science light) | G-CLEF lab data; an unstabilised spectrograph showed up to 8-10 m/s between two fibres over a week (TRES with an astro-comb, Phillips et al. 2012) |
| LSF variation (2D, per fibre, in time) | optics | 2D PSF from comb lines; extraction mode 2 or 3 | static along-order gradient gains nothing at 1 m/s | G-CLEF design; comb data |
| Pixel-position and size irregularities, stitching | detector | detector map dx(p), R(p) | stitching < 0.02 px | comb data; injection |
| Charge-transfer and brighter-fatter effects (flux-dependent shifts) | detector | flux-dependent pixel-shift term | not measured | lab and comb data at several fluxes |
| Fibre modal noise, scrambling, slicer illumination | optics | per-fibre/slice terms, error model; per-exposure illumination LSF kernel | per-telescope breaks after feed changes | simulation: 1% near-field gradient ~6 m/s along dispersion, ~0.3 m/s along slit (x4 in modes 2-3); far field 0.1-0.7 m/s. Needs centroid stability ~2e-5 of the core; G-CLEF lab data |
| Extraction-induced LSF changes (non-separable 2D PSF, slice overlap) | optics/detector | mode 1 with fixed weights (modes 2-3 not needed) | < 1 m/s for bright stars (1D mode); simulation: slice-flux tilts 5% <~1 cm/s; per-frame weights 4-14 cm/s | G-CLEF simulation done |
| Cross-contamination (calibration light in science traces) | detector/extraction | simultaneous trace fitting | leakage <= 1e-3, < 0.2 m/s (too large at 10 cm/s); simulation with PSF wings: 2-12 cm/s per 20% comb-flux change, m/s at 100x star/comb ratio, removed by 2D comb subtraction | G-CLEF simulation; comb data |

Consequences for the code: every term has a frame and a component; no
term is folded into another frame's nuisance parameters without a test
showing it is separable; the template's own uncertainty propagates into
the RVs. MINERVA exercises the star and observatory frames and the
combination stage, and, through the information-content study, how
far iodine itself can go; the optics and detector frames below 1 m/s
of a comb instrument need comb data, so a public comb- or etalon-calibrated dataset is the second test
bed.

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
