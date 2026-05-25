import asyncio
import socket

from asyncua import Client

from src.domain.models import DataType, RuntimeSettings, ServerSettings, SimulatorSettings, SimulatorState, VariableDefinition
from src.infrastructure.asyncua_compat import patch_asyncua_python314_annotations
from src.infrastructure.opcua_browser import BrowserConnection, OpcuaBrowser
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


def test_browser_expands_simulator_variables() -> None:
    values = asyncio.run(_browse_simulator_variables())

    assert values["thermometer"] == 22.0
    assert values["pump_running"] is False


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


async def _browse_simulator_variables() -> dict[str, object]:
    patch_asyncua_python314_annotations()
    endpoint = f"opc.tcp://127.0.0.1:{free_tcp_port()}"
    settings = SimulatorSettings(
        server=ServerSettings(endpoint=endpoint),
        runtime=RuntimeSettings(),
        variables=(
            VariableDefinition("thermometer", "ns=2;s=thermometer", DataType.FLOAT, 22.0),
            VariableDefinition("pump_running", "ns=2;s=pump_running", DataType.BOOLEAN, False),
        ),
    )
    state = SimulatorState(settings)
    server = AsyncuaSimulatorServer()
    await server.start(settings, state)

    try:
        browser = OpcuaBrowser()
        objects = await browser.browse(BrowserConnection(endpoint=endpoint))
        simulator_node = next(
            node for node in objects.node.children if node.display_name == settings.server.object_name
        )
        result = await browser.expand(
            BrowserConnection(endpoint=endpoint),
            node_id=simulator_node.node_id,
            path=simulator_node.path,
            relative_path=simulator_node.relative_path,
            max_depth=3,
            max_nodes=100,
        )
        return {
            node.display_name: node.value
            for node in _flatten(result.node)
            if node.display_name in {"thermometer", "pump_running"}
        }
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


def _flatten(node):
    yield node
    for child in node.children:
        yield from _flatten(child)


def free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
