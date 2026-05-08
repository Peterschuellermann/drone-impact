import pytest
from droneimpact.config import load_config, AppConfig


def pytest_addoption(parser):
    parser.addoption(
        "--run-perf",
        action="store_true",
        default=False,
        help="Run performance benchmark tests (requires real data files)",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "perf: mark test as performance benchmark (skipped without --run-perf)",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-perf"):
        skip_perf = pytest.mark.skip(reason="Pass --run-perf to run performance benchmarks")
        for item in items:
            if "perf" in item.keywords:
                item.add_marker(skip_perf)


@pytest.fixture(scope="session")
def config() -> AppConfig:
    cfg = load_config("config.yaml")
    # Use fewer Monte Carlo samples in tests so the suite runs in seconds, not minutes.
    # Performance tests set their own sample counts explicitly and are unaffected.
    return cfg.model_copy(update={
        "physics": cfg.physics.model_copy(update={"n_monte_carlo_samples": 200})
    })
