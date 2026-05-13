import pytest

from src.domain.models import (
    DataType,
    GeneratorSettings,
    RuntimeSettings,
    ServerSettings,
    SimulatorSettings,
    SimulatorState,
    VariableDefinition,
    coerce_value,
)


def settings(*variables: VariableDefinition) -> SimulatorSettings:
    return SimulatorSettings(
        server=ServerSettings(),
        runtime=RuntimeSettings(),
        variables=variables,
    )


def test_boolean_values_accept_plc_friendly_inputs() -> None:
    assert coerce_value(True, DataType.BOOLEAN) is True
    assert coerce_value(False, DataType.BOOLEAN) is False
    assert coerce_value(1, DataType.BOOLEAN) is True
    assert coerce_value(0, DataType.BOOLEAN) is False
    assert coerce_value("true", DataType.BOOLEAN) is True
    assert coerce_value("0", DataType.BOOLEAN) is False


def test_boolean_values_reject_other_inputs() -> None:
    with pytest.raises(ValueError, match="boolean"):
        coerce_value(2, DataType.BOOLEAN)


def test_int_values_reject_booleans_and_decimals() -> None:
    with pytest.raises(ValueError, match="int"):
        coerce_value(True, DataType.INT)
    with pytest.raises(ValueError, match="int"):
        coerce_value("1.5", DataType.INT)


def test_state_keeps_static_defaults_across_ticks() -> None:
    simulator_settings = settings(
        VariableDefinition("thermometer", "ns=2;s=thermometer", DataType.FLOAT, 22.0)
    )
    state = SimulatorState(simulator_settings)

    state.advance(1)
    state.advance(2)

    assert state.get_variable("thermometer").value == 22.0


def test_state_generates_numeric_values_only_when_configured() -> None:
    simulator_settings = settings(
        VariableDefinition(
            "thermometer",
            "ns=2;s=thermometer",
            DataType.FLOAT,
            22.0,
            generator=GeneratorSettings(kind="sine", amplitude=2.0, period_ticks=4),
        )
    )
    state = SimulatorState(simulator_settings)

    state.advance(1)

    assert state.get_variable("thermometer").value == 24.0


def test_rejects_duplicate_names_and_node_ids() -> None:
    with pytest.raises(ValueError, match="duplicate variable name"):
        settings(
            VariableDefinition("sensor", "ns=2;s=sensor_1", DataType.FLOAT, 1.0),
            VariableDefinition("sensor", "ns=2;s=sensor_2", DataType.FLOAT, 1.0),
        )

    with pytest.raises(ValueError, match="duplicate variable node_id"):
        settings(
            VariableDefinition("sensor_1", "ns=2;s=sensor", DataType.FLOAT, 1.0),
            VariableDefinition("sensor_2", "ns=2;s=sensor", DataType.FLOAT, 1.0),
        )


def test_rejects_generator_for_boolean_variable() -> None:
    with pytest.raises(ValueError, match="generators"):
        VariableDefinition(
            "pump_running",
            "ns=2;s=pump_running",
            DataType.BOOLEAN,
            False,
            generator=GeneratorSettings(kind="sine", amplitude=1.0, period_ticks=2),
        )
