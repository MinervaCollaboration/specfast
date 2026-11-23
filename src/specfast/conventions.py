"""Units, constants and the velocity sign convention.

Everything in specfast follows these rules (they match EXOZIPPy, see
DESIGN.md "EXOZIPPy"):

- Velocities are in **m/s**. Wavelengths are **vacuum**, in Angstrom unless a
  name says otherwise. Times are **BJD_TDB** (days) for anything that leaves
  a stage; raw headers in UTC are converted in the header layer.
- **Positive velocity = receding = redshift.** A star with ``v > 0`` has its
  lines at longer wavelengths.
- A "velocity" that comes out of a spectrum fit is a *redshift velocity*
  ``v = c z`` (as barycorrpy and EXOZIPPy's ``raw_redshift`` define it), not a
  physical radial velocity. Redshifts compose multiplicatively, never by
  adding velocities:

      1 + z_obs = (1 + z_1)(1 + z_2)

- The **barycentric correction** ``z_B`` is the redshift that takes a measured
  (topocentric) redshift ``z_meas`` to the barycentric one (Wright & Eastman
  2014, eq. 28 with the target terms left to the model):

      v_bary = c [(1 + z_meas)(1 + z_B) - 1]

  so the observed spectrum of a star with barycentric redshift velocity
  ``v_bary`` is the rest-frame spectrum stretched by

      1 + z_meas = (1 + v_bary / c) / (1 + z_B).

  In the forward model the star is evaluated at ``lambda_obs * D`` with the
  Doppler factor ``D = 1 / (1 + z_meas)`` (DESIGN.md, "The forward model").
"""

from __future__ import annotations

import numpy as np

#: Speed of light [m/s] (exact, SI).
C_MPS = 299_792_458.0
#: Speed of light [km/s].
C_KMS = C_MPS / 1e3

#: Time scale and format of every time that leaves a stage.
TIME_SCALE = "tdb"
TIME_FORMAT = "BJD"


def velocity_to_redshift(v):
    """Redshift ``z = v / c`` of a redshift velocity ``v`` [m/s]."""
    return np.asarray(v) / C_MPS


def redshift_to_velocity(z):
    """Redshift velocity ``v = c z`` [m/s] of a redshift ``z``."""
    return np.asarray(z) * C_MPS


def relativistic_doppler_factor(v_radial):
    """``1 + z`` for a *physical* radial velocity [m/s] along the line of sight.

    Special-relativistic, purely radial motion: ``sqrt((1 + b) / (1 - b))``
    with ``b = v / c``; positive (receding) gives ``1 + z > 1``. Use this to
    turn a physical velocity into a redshift; fitted velocities are already
    redshift velocities and need no such conversion.
    """
    b = np.asarray(v_radial) / C_MPS
    return np.sqrt((1.0 + b) / (1.0 - b))


def compose_redshifts(*zs):
    """Total redshift of successive shifts: ``prod(1 + z_i) - 1``."""
    total = np.asarray(1.0)
    for z in zs:
        total = total * (1.0 + np.asarray(z))
    return total - 1.0


def measured_redshift(v_bary, z_bary):
    """Topocentric redshift ``z_meas`` of a star with barycentric redshift
    velocity ``v_bary`` [m/s] observed with barycentric correction ``z_bary``.
    """
    return (1.0 + np.asarray(v_bary) / C_MPS) / (1.0 + np.asarray(z_bary)) - 1.0


def barycentric_velocity(z_meas, z_bary):
    """Barycentric redshift velocity [m/s] from a measured redshift and the
    barycentric correction: ``c [(1 + z_meas)(1 + z_bary) - 1]``."""
    return C_MPS * ((1.0 + np.asarray(z_meas)) * (1.0 + np.asarray(z_bary)) - 1.0)


def doppler_factor(v_bary, z_bary=0.0):
    """Forward-model Doppler factor ``D = 1 / (1 + z_meas)``.

    The stellar rest-frame spectrum ``S`` is evaluated at ``lambda_obs * D``.
    ``v_bary`` [m/s] is the barycentric redshift velocity, ``z_bary`` the
    barycentric correction of the exposure.
    """
    return 1.0 / (1.0 + measured_redshift(v_bary, z_bary))


def ln_shift(v_bary, z_bary=0.0):
    """``ln(1 + z_meas)``: the shift in ln(lambda) of the stellar spectrum.

    A rest-frame spectrum tabulated in ln(lambda) appears in the observed
    frame at ``ln(lambda_rest) + ln_shift``.
    """
    return np.log1p(np.asarray(v_bary) / C_MPS) - np.log1p(np.asarray(z_bary))
