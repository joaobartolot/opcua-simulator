from typing import Any

from asyncua import Server, ua

from src.domain.models import DataType, SimulatorSettings, SimulatorState
from src.infrastructure.asyncua_compat import patch_asyncua_python314_annotations
from src.infrastructure.logger import get_logger


LOGGER = get_logger(__name__)


class AsyncuaSimulatorServer:
    def __init__(self) -> None:
        self._server: Server | None = None
        self._variables: dict[str, Any] = {}
        self._device: Any | None = None

    async def start(self, settings: SimulatorSettings, state: SimulatorState) -> None:
        patch_asyncua_python314_annotations()
        server = Server()
        await server.init()
        patch_asyncua_python314_annotations()

        server.set_endpoint(settings.server.endpoint)
        namespace_index = await server.register_namespace(settings.server.namespace_uri)
        device = await server.nodes.objects.add_object(
            namespace_index,
            settings.server.object_name,
        )
        self._device = device

        self._variables = {}
        for variable in state.list_variables():
            await self.add_variable(variable)

        await server.start()
        patch_asyncua_python314_annotations()
        self._server = server

        LOGGER.info("OPC UA simulator listening endpoint=%s", settings.server.endpoint)
        for variable in state.list_variables():
            LOGGER.info(
                "simulator tag name=%s node_id=%s type=%s unit=%s",
                variable.name,
                variable.node_id,
                variable.data_type.value,
                variable.unit or "",
            )

    async def sync(self, state: SimulatorState) -> None:
        for variable in state.list_variables():
            await self._variables[variable.name].write_value(
                variable.value,
                _variant_type(variable.data_type),
            )

    async def add_variable(self, variable: Any) -> None:
        if variable.name in self._variables:
            return
        if self._device is None:
            raise RuntimeError("OPC UA simulator server is not started")

        node_id = ua.NodeId.from_string(variable.node_id)
        node = await self._device.add_variable(
            node_id,
            variable.name,
            variable.value,
            _variant_type(variable.data_type),
        )
        if variable.definition.writable:
            await node.set_writable()
        self._variables[variable.name] = node

    async def stop(self) -> None:
        if self._server is None:
            return
        server = self._server
        self._server = None
        self._variables = {}
        self._device = None
        await server.stop()


def _variant_type(data_type: DataType) -> ua.VariantType:
    if data_type == DataType.BOOLEAN:
        return ua.VariantType.Boolean
    if data_type == DataType.INT:
        return ua.VariantType.Int64
    if data_type == DataType.FLOAT:
        return ua.VariantType.Double
    if data_type == DataType.STRING:
        return ua.VariantType.String
    raise ValueError(f"unsupported data type: {data_type}")
