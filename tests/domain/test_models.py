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
    generated_value,
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


def test_totalizer_accumulates_liters_from_runtime_interval() -> None:
    simulator_settings = SimulatorSettings(
        server=ServerSettings(),
        runtime=RuntimeSettings(update_interval_ms=500),
        variables=(
            VariableDefinition(
                "liters_total",
                "ns=2;s=liters_total",
                DataType.FLOAT,
                0.0,
                generator=GeneratorSettings(
                    kind="totalizer",
                    rate_liters_per_minute=60.0,
                ),
            ),
        ),
    )
    state = SimulatorState(simulator_settings)

    state.advance(0)
    state.advance(1)

    assert state.get_variable("liters_total").value == 1.0


def test_totalizer_pauses_while_linked_boolean_is_false() -> None:
    simulator_settings = SimulatorSettings(
        server=ServerSettings(),
        runtime=RuntimeSettings(update_interval_ms=1000),
        variables=(
            VariableDefinition("valve_open", "ns=2;s=valve_open", DataType.BOOLEAN, False),
            VariableDefinition(
                "liters_total",
                "ns=2;s=liters_total",
                DataType.FLOAT,
                0.0,
                generator=GeneratorSettings(
                    kind="totalizer",
                    rate_liters_per_minute=60.0,
                    enabled_by="valve_open",
                ),
            ),
        ),
    )
    state = SimulatorState(simulator_settings)

    state.advance(0)
    state.set_value("valve_open", True)
    state.advance(1)
    state.set_value("valve_open", False)
    state.advance(2)

    assert state.get_variable("liters_total").value == 1.0


def test_rejects_invalid_totalizer_settings() -> None:
    with pytest.raises(ValueError, match="rate_liters_per_minute"):
        GeneratorSettings(kind="totalizer", rate_liters_per_minute=0.0)


def test_rejects_generator_link_to_non_boolean_variable() -> None:
    with pytest.raises(ValueError, match="enabled_by must reference a boolean"):
        settings(
            VariableDefinition("flow", "ns=2;s=flow", DataType.FLOAT, 0.0),
            VariableDefinition(
                "liters_total",
                "ns=2;s=liters_total",
                DataType.FLOAT,
                0.0,
                generator=GeneratorSettings(
                    kind="totalizer",
                    rate_liters_per_minute=60.0,
                    enabled_by="flow",
                ),
            ),
        )


def test_generated_totalizer_value_can_be_calculated_directly() -> None:
    definition = VariableDefinition(
        "liters_total",
        "ns=2;s=liters_total",
        DataType.FLOAT,
        10.0,
        generator=GeneratorSettings(kind="totalizer", rate_liters_per_minute=30.0),
    )

    assert generated_value(
        definition,
        0,
        current_value=10.0,
        update_interval_ms=1000,
    ) == 10.5


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
