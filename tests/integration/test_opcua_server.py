import asyncio
import socket

from asyncua import Client

from src.domain.models import DataType, RuntimeSettings, ServerSettings, SimulatorSettings, SimulatorState, VariableDefinition
from src.infrastructure.asyncua_compat import patch_asyncua_python314_annotations
from src.infrastructure.opcua_server import AsyncuaSimulatorServer


def test_client_reads_configured_typed_variables() -> None:
    readings = asyncio.run(_read_configured_variables())

    assert readings == {
        "thermometer": 22.0,
        "pump_running": False,
        "batch_count": 3,
        "status": "ready",
    }


def test_client_reads_runtime_added_variable() -> None:
    value = asyncio.run(_read_runtime_added_variable())

    assert value == 42


async def _read_runtime_added_variable() -> object:
    patch_asyncua_python314_annotations()
    endpoint = f"opc.tcp://127.0.0.1:{free_tcp_port()}"
    settings = SimulatorSettings(
        server=ServerSettings(endpoint=endpoint),
        runtime=RuntimeSettings(),
        variables=(
            VariableDefinition("status", "ns=2;s=status", DataType.STRING, "ready"),
        ),
    )
    state = SimulatorState(settings)
    server = AsyncuaSimulatorServer()
    await server.start(settings, state)

    try:
        variable = state.add_variable(
            VariableDefinition(
                "runtime_count",
                "ns=2;s=runtime_count",
                DataType.INT,
                42,
            )
        )
        await server.add_variable(variable)
        await server.sync(state)
        async with Client(url=endpoint) as client:
            return await client.get_node("ns=2;s=runtime_count").read_value()
    finally:
        await server.stop()


async def _read_configured_variables() -> dict[str, object]:
    patch_asyncua_python314_annotations()
    endpoint = f"opc.tcp://127.0.0.1:{free_tcp_port()}"
    settings = SimulatorSettings(
        server=ServerSettings(endpoint=endpoint),
        runtime=RuntimeSettings(),
        variables=(
            VariableDefinition("thermometer", "ns=2;s=thermometer", DataType.FLOAT, 22.0),
            VariableDefinition("pump_running", "ns=2;s=pump_running", DataType.BOOLEAN, False),
            VariableDefinition("batch_count", "ns=2;s=batch_count", DataType.INT, 3),
            VariableDefinition("status", "ns=2;s=status", DataType.STRING, "ready"),
        ),
    )
    state = SimulatorState(settings)
    server = AsyncuaSimulatorServer()
    await server.start(settings, state)

    try:
        async with Client(url=endpoint) as client:
            return {
                variable.name: await client.get_node(variable.node_id).read_value()
                for variable in state.list_variables()
            }
    finally:
        await server.stop()


def free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
