"""specfast: precise radial velocities from echelle spectra.

Two stages around one on-disk contract (DESIGN.md):

    raw frames --[extract]--> ExtractedSpectrum --[doppler]--> velocities

Modules: ``conventions`` (units, sign convention), ``config`` (run config),
``provenance``, ``instrument`` (instrument description as data),
``products`` (ExtractedSpectrum), ``extract`` (stage 1), ``doppler``
(stage 2 forward model), ``combine`` (joint offset/error-model solve).
"""

__version__ = "0.0.1"
