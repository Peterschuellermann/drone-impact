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
    return load_config("config.yaml")
