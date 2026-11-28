"""Converters from other pipelines' extracted spectra to an ExtractedSpectrum.

DESIGN.md, "Two stages, one repository": either stage can be replaced, so
the Doppler stage can run on another pipeline's extraction once it is
converted to :class:`~specfast.products.ExtractedSpectrum`.

- :mod:`~specfast.converters.neid`: NEID L1 (and the L1 part of L2) files.
- :mod:`~specfast.converters.nres`: LCO NRES BANZAI-NRES ``e92-1d`` files and
  master arcs.
"""
