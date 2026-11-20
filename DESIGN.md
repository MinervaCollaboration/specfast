# MINERVA iodine RV pipeline: architecture (draft 0, 2026-11-20)

Status: proposal for discussion. Nothing here is implemented yet. The
test bed for experiments is Charlie's code; this repository is the
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
4. No silent failures, no hidden global state, no environment variables
   that change the science; every product records its provenance.

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
then integrated onto pixels.

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
| LSF | Gaussian, sigma per (fibre, order) frozen from the B-star calibration, sigma linear in x | Gauss-Hermite or sum of Gaussians; shape from the optical model times a fitted perturbation |
| Iodine | FTS atlas, optical-depth strength | per-era atlas, cell temperature term |
| Telluric | mask from an atlas at a configurable depth | fitted H2O and O2 columns per exposure from a line-list model (TAPAS / molecfit style); mask only saturated cores |
| Star | DSST template; inferred template | Korg synthetic spectrum from (Teff, logg, abundances, vsini, macroturbulence) |
| Continuum | low-order polynomial times a blaze function | spline |
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

## Open questions

- The KiwiSpec optical model: the Zemax file is a black box. Can it
  export a table of (order, wavelength, fibre) -> (x, y, spot size)?
  The KiwiSpec papers give the grating and camera parameters.
- Era break list: which instrument interventions moved the offsets?
- Repository name and the MinervaCollaboration org (not created yet).
