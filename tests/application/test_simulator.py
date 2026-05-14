import threading

from src.application.simulator import run_simulator
from src.domain.models import DataType, RuntimeSettings, ServerSettings, SimulatorSettings, VariableDefinition


class FakeServer:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.synced_values: list[dict[str, object]] = []

    async def start(self, settings, state) -> None:
        self.started = True

    async def sync(self, state) -> None:
        self.synced_values.append(
            {variable.name: variable.value for variable in state.list_variables()}
        )

    async def add_variable(self, variable) -> None:
        return None

    async def stop(self) -> None:
        self.stopped = True


async def no_sleep(_: float) -> None:
    stop_requested.set()


stop_requested = threading.Event()


def test_run_simulator_starts_syncs_and_stops() -> None:
    import asyncio

    stop_requested.clear()
    server = FakeServer()
    settings = SimulatorSettings(
        server=ServerSettings(),
        runtime=RuntimeSettings(update_interval_ms=1),
        variables=(
            VariableDefinition("status", "ns=2;s=status", DataType.STRING, "ready"),
        ),
    )

    asyncio.run(
        run_simulator(
            settings,
            server,
            stop_requested=stop_requested,
            sleep=no_sleep,
        )
    )

    assert server.started is True
    assert server.stopped is True
    assert server.synced_values == [{"status": "ready"}]
