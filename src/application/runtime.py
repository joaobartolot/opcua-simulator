import asyncio
from contextlib import suppress
from typing import Any

from src.application.simulator import Sleep, SimulatorServer
from src.domain.models import (
    DataType,
    GeneratorSettings,
    SimulatorSettings,
    SimulatorState,
    SimulatorVariable,
    VariableDefinition,
)


RUNTIME_NODE_ID_TEMPLATE = "ns=2;s={name}"


class SimulatorRuntime:
    """Shared runtime for OPC UA syncing and control adapters."""

    def __init__(
        self,
        settings: SimulatorSettings,
        server: SimulatorServer,
        *,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.settings = settings
        self.state = SimulatorState(settings)
        self._server = server
        self._sleep = sleep
        self._sync_lock = asyncio.Lock()
        self._stop_requested = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._started = False

    @property
    def started(self) -> bool:
        return self._started

    async def start(self) -> None:
        if self._started:
            return

        await self._server.start(self.settings, self.state)
        self._stop_requested.clear()
        self._task = asyncio.create_task(self._run_loop())
        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return

        self._stop_requested.set()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        self._task = None
        self._started = False
        await self._server.stop()

    def list_variables(self) -> list[SimulatorVariable]:
        return self.state.list_variables()

    def get_variable(self, name: str) -> SimulatorVariable:
        return self.state.get_variable(name)

    async def set_value(self, name: str, value: Any) -> SimulatorVariable:
        variable = self.state.get_variable(name)
        if not variable.definition.writable:
            raise PermissionError(f"variable is read-only: {name}")

        async with self._sync_lock:
            self.state.set_value(name, value)
            await self._server.sync(self.state)
        return self.state.get_variable(name)

    async def set_auto_update(self, name: str, enabled: bool) -> SimulatorVariable:
        async with self._sync_lock:
            self.state.set_auto_update(name, enabled)
            await self._server.sync(self.state)
        return self.state.get_variable(name)

    async def add_variable(
        self,
        *,
        name: str,
        data_type: DataType,
        default: Any,
        node_id: str | None = None,
        unit: str | None = None,
        writable: bool = True,
        generator: GeneratorSettings | None = None,
    ) -> SimulatorVariable:
        definition = VariableDefinition(
            name=name,
            node_id=node_id or RUNTIME_NODE_ID_TEMPLATE.format(name=name),
            data_type=data_type,
            default=default,
            unit=unit,
            writable=writable,
            generator=generator,
        )
        async with self._sync_lock:
            variable = self.state.add_variable(definition)
            await self._server.add_variable(variable)
            await self._server.sync(self.state)
            return self.state.get_variable(variable.name)

    async def _run_loop(self) -> None:
        tick = 0
        while not self._stop_requested.is_set():
            async with self._sync_lock:
                self.state.advance(tick)
                await self._server.sync(self.state)
            tick += 1
            await self._sleep(self.settings.runtime.update_interval_ms / 1000)
