import asyncio

import pytest

from src.application.runtime import SimulatorRuntime
from src.domain.models import (
    DataType,
    GeneratorSettings,
    RuntimeSettings,
    ServerSettings,
    SimulatorSettings,
    VariableDefinition,
)


class FakeServer:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.added_variables: list[str] = []
        self.synced_values: list[dict[str, object]] = []

    async def start(self, settings, state) -> None:
        self.started = True

    async def sync(self, state) -> None:
        self.synced_values.append(
            {variable.name: variable.value for variable in state.list_variables()}
        )

    async def add_variable(self, variable) -> None:
        self.added_variables.append(variable.name)

    async def stop(self) -> None:
        self.stopped = True


async def long_sleep(_: float) -> None:
    await asyncio.sleep(60)


def test_runtime_updates_shared_state_and_syncs_server() -> None:
    asyncio.run(_test_runtime_updates_shared_state_and_syncs_server())


async def _test_runtime_updates_shared_state_and_syncs_server() -> None:
    server = FakeServer()
    runtime = SimulatorRuntime(_settings(), server, sleep=long_sleep)
    await runtime.start()

    try:
        updated = await runtime.set_value("thermometer", "25.5")
    finally:
        await runtime.stop()

    assert updated.value == 25.5
    assert server.started is True
    assert server.stopped is True
    assert server.synced_values[-1]["thermometer"] == 25.5


def test_runtime_rejects_read_only_manual_update() -> None:
    asyncio.run(_test_runtime_rejects_read_only_manual_update())


async def _test_runtime_rejects_read_only_manual_update() -> None:
    runtime = SimulatorRuntime(_settings(), FakeServer(), sleep=long_sleep)
    await runtime.start()

    try:
        with pytest.raises(PermissionError):
            await runtime.set_value("status", "running")
    finally:
        await runtime.stop()


def test_runtime_sets_auto_mode_for_generated_variables() -> None:
    asyncio.run(_test_runtime_sets_auto_mode_for_generated_variables())


async def _test_runtime_sets_auto_mode_for_generated_variables() -> None:
    runtime = SimulatorRuntime(_settings(), FakeServer(), sleep=long_sleep)
    await runtime.start()

    try:
        updated = await runtime.set_auto_update("wave", False)
    finally:
        await runtime.stop()

    assert updated.auto_update is False


def test_runtime_adds_temporary_variable_and_syncs_server() -> None:
    asyncio.run(_test_runtime_adds_temporary_variable_and_syncs_server())


async def _test_runtime_adds_temporary_variable_and_syncs_server() -> None:
    server = FakeServer()
    runtime = SimulatorRuntime(_settings(), server, sleep=long_sleep)
    await runtime.start()

    try:
        created = await runtime.add_variable(
            name="runtime_sensor",
            data_type=DataType.INT,
            default="7",
        )
    finally:
        await runtime.stop()

    assert created.name == "runtime_sensor"
    assert created.node_id == "ns=2;s=runtime_sensor"
    assert created.value == 7
    assert "runtime_sensor" in server.added_variables
    assert server.synced_values[-1]["runtime_sensor"] == 7


def test_runtime_rejects_duplicate_runtime_variable() -> None:
    asyncio.run(_test_runtime_rejects_duplicate_runtime_variable())


async def _test_runtime_rejects_duplicate_runtime_variable() -> None:
    runtime = SimulatorRuntime(_settings(), FakeServer(), sleep=long_sleep)
    await runtime.start()

    try:
        await runtime.add_variable(
            name="runtime_sensor",
            data_type=DataType.FLOAT,
            default=1.0,
            node_id="ns=2;s=runtime_sensor",
        )
        with pytest.raises(ValueError, match="duplicate variable node_id"):
            await runtime.add_variable(
                name="runtime_sensor_2",
                data_type=DataType.FLOAT,
                default=1.0,
                node_id="ns=2;s=runtime_sensor",
            )
    finally:
        await runtime.stop()


def _settings() -> SimulatorSettings:
    return SimulatorSettings(
        server=ServerSettings(endpoint="opc.tcp://127.0.0.1:4840"),
        runtime=RuntimeSettings(update_interval_ms=1000),
        variables=(
            VariableDefinition("thermometer", "ns=2;s=thermometer", DataType.FLOAT, 22.0),
            VariableDefinition(
                "status",
                "ns=2;s=status",
                DataType.STRING,
                "ready",
                writable=False,
            ),
            VariableDefinition(
                "wave",
                "ns=2;s=wave",
                DataType.FLOAT,
                1.0,
                generator=GeneratorSettings(kind="sine", amplitude=1.0, period_ticks=10),
            ),
        ),
    )
