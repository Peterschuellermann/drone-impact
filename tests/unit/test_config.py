import pytest
from pathlib import Path
from droneimpact.config import load_config, AppConfig


def test_load_config_returns_app_config(config):
    assert isinstance(config, AppConfig)


def test_config_version(config):
    assert config.version == "1.0"


def test_monte_carlo_samples():
    # Load directly to check the config.yaml default, not the test-overridden fixture value.
    cfg = load_config("config.yaml")
    assert cfg.physics.n_monte_carlo_samples == 10000


def test_p_kill(config):
    assert config.engagement.p_kill == pytest.approx(0.50)


def test_mode_weights_sum_to_one(config):
    w = config.engagement.mode_weights
    total = w.propulsion_loss + w.loss_of_control + w.break_apart
    assert abs(total - 1.0) < 1e-6


def test_blast_radii_positive(config):
    assert config.casualty.blast.lethal_radius_m > 0
    assert config.casualty.blast.injury_radius_m > config.casualty.blast.lethal_radius_m


def test_frag_radii_positive(config):
    assert config.casualty.fragmentation.lethal_radius_m > 0
    assert config.casualty.fragmentation.danger_radius_m > config.casualty.fragmentation.lethal_radius_m


def test_shahed_params(config):
    s = config.physics.shahed136
    assert s.mass_kg == pytest.approx(200.0)
    assert s.glide_ratio == pytest.approx(5.0)
    assert s.cruise_speed_m_s == pytest.approx(51.4)


def test_missing_required_field_raises(tmp_path):
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("version: '1.0'\nphysics: {}\n")
    with pytest.raises(Exception):
        load_config(bad_yaml)


def test_mode_weights_not_summing_raises(tmp_path):
    import yaml
    from droneimpact.config import load_config

    # Load current config as dict and mutate weights
    with open("config.yaml") as f:
        raw = yaml.safe_load(f)
    raw["engagement"]["mode_weights"]["propulsion_loss"] = 0.99
    bad = tmp_path / "bad_weights.yaml"
    bad.write_text(yaml.dump(raw))
    with pytest.raises(Exception, match="sum"):
        load_config(bad)
