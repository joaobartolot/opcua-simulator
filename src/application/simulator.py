import asyncio
import threading
from collections.abc import Awaitable, Callable
from typing import Protocol

from src.domain.models import SimulatorSettings, SimulatorState


Sleep = Callable[[float], Awaitable[None]]


class SimulatorServer(Protocol):
    async def start(self, settings: SimulatorSettings, state: SimulatorState) -> None:
        """Start the external OPC UA server."""

    async def sync(self, state: SimulatorState) -> None:
        """Write current simulator state to exposed OPC UA variables."""

    async def stop(self) -> None:
        """Stop the external OPC UA server."""


async def run_simulator(
    settings: SimulatorSettings,
    server: SimulatorServer,
    *,
    stop_requested: threading.Event | None = None,
    sleep: Sleep = asyncio.sleep,
) -> None:
    state = SimulatorState(settings)
    await run_simulator_state(
        settings,
        state,
        server,
        stop_requested=stop_requested,
        sleep=sleep,
    )


async def run_simulator_state(
    settings: SimulatorSettings,
    state: SimulatorState,
    server: SimulatorServer,
    *,
    stop_requested: threading.Event | None = None,
    sleep: Sleep = asyncio.sleep,
) -> None:
    await server.start(settings, state)
    tick = 0

    try:
        while stop_requested is None or not stop_requested.is_set():
            state.advance(tick)
            await server.sync(state)
            tick += 1
            await sleep(settings.runtime.update_interval_ms / 1000)
    finally:
        await server.stop()
