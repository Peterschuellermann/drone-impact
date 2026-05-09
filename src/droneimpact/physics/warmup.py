from __future__ import annotations

import numpy as np


def warmup_jit() -> None:
    """Call each Numba kernel with tiny inputs to trigger JIT compilation."""
    from droneimpact.physics.m1 import _m1_kernel
    from droneimpact.physics.m2 import _m2_kernel
    from droneimpact.physics.m3 import _m3_kernel

    n = 4

    _m1_kernel(
        np.zeros(n), np.ones(n), np.ones(n) * 50.0, 100.0,
    )

    _m2_kernel(
        np.zeros(n), np.ones(n) * 5.0,
        np.zeros((10, n)),
        100.0, 50.0, 1.5, 1.0, 10,
        0.007, 8500.0, 1.225, 9.81,
    )

    _m3_kernel(
        np.ones(n) * 10.0, np.ones(n) * 10.0, np.ones(n) * -5.0,
        np.ones(n) * 0.007,
        100.0, 0.1, 10,
        8500.0, 1.225, 9.81,
    )
