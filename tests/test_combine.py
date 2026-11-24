"""Joint offset / error-model combination (specfast.combine)."""

import numpy as np

from specfast.combine import SegmentVelocities, combine, era_zero_points


def test_combine_recovers_rvs_offsets_and_error_model():
    rng = np.random.default_rng(1)
    ne, ng = 40, 12
    rv = rng.normal(0, 5, ne)
    rv -= rv.mean()
    off = rng.normal(0, 50, (ng, 2))
    rows = []
    for e in range(ne):
        era = int(e >= ne // 2)
        for g in range(ng):
            sig = rng.uniform(5, 15)
            v = rv[e] + off[g, era] + rng.normal(0, np.hypot(0.8 * sig, 3.0))
            rows.append((e, f"g{g}", era, v, sig))
    e, g, era, v, s = (np.array(x) for x in zip(*rows, strict=True))
    v[7] += 500.0  # an outlier
    res = combine(SegmentVelocities(e, g, era, v, s))
    assert not res.keep[7]
    # a constant per era is degenerate with that era's offsets: compare
    # within eras
    d = res.rv - rv
    half = ne // 2
    d = np.r_[d[:half] - d[:half].mean(), d[half:] - d[half:].mean()]
    assert np.std(d) < 4.0  # ~9 m/s per value over 12 groups
    assert 0.6 < res.beta < 1.0 and 1.5 < res.jitter < 4.5
    assert res.covariance.shape == (ne, ne)


def test_era_zero_points():
    mjd = np.arange(10.0)
    rv = np.r_[np.zeros(5), np.full(5, 7.0)]
    out, zp = era_zero_points(mjd, rv, np.ones(10), [4.5])
    assert np.allclose(out, 0) and np.allclose(zp, [0, 7])
