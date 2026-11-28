"""Line statistics helpers."""

import numpy as np

from specfast.linestats import block_bootstrap, combine_lines, excess_ml, group_means, wrms


def test_excess_ml_recovers_tau():
    rng = np.random.default_rng(1)
    e = rng.uniform(0.5, 1.5, 4000)
    x = 3.0 + rng.normal(0, np.sqrt(e**2 + 0.8**2))
    assert abs(excess_ml(x, e) - 0.8) < 0.08
    x0 = rng.normal(0, e)
    assert excess_ml(x0, e) < 0.15
    assert np.isnan(excess_ml([1.0, 2.0], [1.0, 1.0]))


def test_group_means_and_combine():
    g = np.array([0, 0, 1, 1, 1])
    x = np.array([1.0, 3.0, 2.0, 2.0, np.nan])
    e = np.array([1.0, 1.0, 1.0, 2.0, 1.0])
    ug, m, s = group_means(g, x, e)
    assert np.allclose(m, [2.0, 2.0])
    assert np.allclose(s, [1 / np.sqrt(2), 1 / np.sqrt(1.25)])
    vel = np.array([[1.0, 3.0, 100.0]])
    sig = np.array([[1.0, 1.0, 1.0]])
    v, ev = combine_lines(vel, sig, mask=np.array([True, True, False]))
    assert np.allclose(v, 2.0) and np.allclose(ev, 1 / np.sqrt(2))
    v2, _ = combine_lines(vel, sig, extra=np.array([0.0, 0.0, 1e6]))
    assert abs(v2[0] - 2.0) < 1e-6
    rng = np.random.default_rng(3)
    vv = rng.normal(0, 1, (4, 200))
    vv[:, 7] = 500.0  # one wild line
    v3, _ = combine_lines(vv, np.ones_like(vv), clip=5.0)
    v4, _ = combine_lines(vv, np.ones_like(vv))
    assert np.all(np.abs(v3) < 0.3) and np.all(v4 > 2.0)


def test_wrms_and_bootstrap():
    assert np.isclose(wrms([1.0, -1.0]), 1.0)
    b = block_bootstrap(lambda idx: idx.size, 7, n_boot=5)
    assert b.shape == (5,) and np.all(b == 7)
