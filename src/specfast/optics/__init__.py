"""Optical-design tools: from a Zemax design to an instrument description.

Pieces (each usable alone):

- :mod:`specfast.optics.zar`: unpack a Zemax archive (``.zar``);
- :mod:`specfast.optics.zmx`: parse a sequential lens file (``.zmx``),
  including multi-configuration operands and pickups;
- :mod:`specfast.optics.glass`: glass catalogues (``.agf``);
- :mod:`specfast.optics.trace`: a 3-D sequential ray tracer with Zemax
  coordinate-break and grating rules, and stand-ins for black boxes;
- :mod:`specfast.optics.echellogram`: orders, wavelengths and trace positions
  on each detector;
- :mod:`specfast.optics.emit`: write an instrument YAML that
  :func:`specfast.instrument.load_instrument` reads;
- :mod:`specfast.optics.cli`: the ``specfast-zemax2instrument`` command.

Privacy: design files, the stand-in parameters derived from them and every
intermediate product belong to whoever owns the design. This package holds
only generic code; it reads its inputs from paths given on the command line
and has no built-in data paths. Encrypted black boxes (``.ZBB``) are never
decrypted: the user describes a stand-in for each one.
"""
