from pathlib import Path

import pytest
from pydantic import ValidationError

from src.domain.models import DataType
from src.infrastructure.config import load_settings


def write_config(path: Path, variables: str | None = None) -> None:
    variable_config = variables or """
  - name: thermometer
    data_type: float
    default: 22.0
    unit: celsius
  - name: pump_running
    data_type: boolean
    default: 1
"""
    path.write_text(
        f"""
server:
  endpoint: opc.tcp://127.0.0.1:4840
  namespace_uri: urn:test-simulator
  object_name: TestSimulator

node_id_template: ns=2;s={{name}}

runtime:
  update_interval_ms: 250

variables:
{variable_config}
""",
        encoding="utf-8",
    )


def test_loads_simulator_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "simulator.yaml"
    write_config(config_path)

    settings = load_settings(config_path)

    assert settings.server.endpoint == "opc.tcp://127.0.0.1:4840"
    assert settings.server.namespace_uri == "urn:test-simulator"
    assert settings.server.object_name == "TestSimulator"
    assert settings.runtime.update_interval_ms == 250
    assert settings.variables[0].name == "thermometer"
    assert settings.variables[0].node_id == "ns=2;s=thermometer"
    assert settings.variables[0].data_type == DataType.FLOAT
    assert settings.variables[1].node_id == "ns=2;s=pump_running"
    assert settings.variables[1].default is True


def test_explicit_node_id_overrides_template(tmp_path: Path) -> None:
    config_path = tmp_path / "simulator.yaml"
    write_config(
        config_path,
        """
  - name: external_sensor
    node_id: ns=4;s=Device.Custom.Sensor
    data_type: float
    default: 10.0
""",
    )

    settings = load_settings(config_path)

    assert settings.variables[0].node_id == "ns=4;s=Device.Custom.Sensor"


def test_loads_totalizer_generator_with_boolean_link(tmp_path: Path) -> None:
    config_path = tmp_path / "simulator.yaml"
    write_config(
        config_path,
        """
  - name: valve_open
    data_type: boolean
    default: false
  - name: liters_total
    data_type: float
    default: 0.0
    unit: liters
    generator:
      kind: totalizer
      rate_liters_per_minute: 42.0
      enabled_by: valve_open
""",
    )

    settings = load_settings(config_path)

    generator = settings.variables[1].generator
    assert generator is not None
    assert generator.kind == "totalizer"
    assert generator.rate_liters_per_minute == 42.0
    assert generator.enabled_by == "valve_open"


def test_env_config_path_selects_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "selected.yaml"
    write_config(config_path)
    monkeypatch.setenv("SIMULATOR_CONFIG_PATH", str(config_path))

    settings = load_settings()

    assert settings.server.object_name == "TestSimulator"


def test_rejects_invalid_variable_config(tmp_path: Path) -> None:
    config_path = tmp_path / "simulator.yaml"
    write_config(
        config_path,
        """
  - name: bad name
    data_type: boolean
    default: 2
""",
    )

    with pytest.raises(ValidationError):
        load_settings(config_path)


def test_rejects_node_id_template_without_name_placeholder(tmp_path: Path) -> None:
    config_path = tmp_path / "simulator.yaml"
    write_config(config_path)
    text = config_path.read_text(encoding="utf-8")
    config_path.write_text(
        text.replace("node_id_template: ns=2;s={name}", "node_id_template: ns=2;s=sensor"),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_settings(config_path)


def test_rejects_duplicate_node_ids(tmp_path: Path) -> None:
    config_path = tmp_path / "simulator.yaml"
    write_config(
        config_path,
        """
  - name: sensor_1
    node_id: ns=2;s=sensor
    data_type: float
    default: 1.0
  - name: sensor_2
    node_id: ns=2;s=sensor
    data_type: float
    default: 2.0
""",
    )

    with pytest.raises(ValidationError):
        load_settings(config_path)


def test_rejects_totalizer_link_to_missing_variable(tmp_path: Path) -> None:
    config_path = tmp_path / "simulator.yaml"
    write_config(
        config_path,
        """
  - name: liters_total
    data_type: float
    default: 0.0
    generator:
      kind: totalizer
      rate_liters_per_minute: 60.0
      enabled_by: valve_open
""",
    )

    with pytest.raises(ValidationError):
        load_settings(config_path)


def test_rejects_non_mapping_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "simulator.yaml"
    config_path.write_text("- nope\n", encoding="utf-8")

    with pytest.raises(ValidationError):
        load_settings(config_path)
