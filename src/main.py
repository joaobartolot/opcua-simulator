import argparse
import asyncio
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from src.application.simulator import run_simulator
from src.dev.simulator_tui import run_simulator_tui
from src.domain.models import SimulatorSettings
from src.infrastructure.config import load_settings
from src.infrastructure.logger import configure_logging
from src.infrastructure.opcua_server import AsyncuaSimulatorServer


SettingsLoader = Callable[[str | Path | None], SimulatorSettings]
SimulatorRunner = Callable[[SimulatorSettings], None]


def simulator_main(
    argv: Sequence[str] | None = None,
    *,
    settings_loader: SettingsLoader = load_settings,
    simulator_runner: SimulatorRunner | None = None,
    simulator_tui_runner: SimulatorRunner = run_simulator_tui,
) -> int:
    args = _parse_args(argv)
    log_level = os.getenv("LOG_LEVEL", "INFO")
    configure_logging(log_level)
    settings = settings_loader(args.config)

    try:
        if args.tui:
            simulator_tui_runner(settings)
        else:
            if simulator_runner is not None:
                simulator_runner(settings)
            else:
                asyncio.run(run_simulator(settings, AsyncuaSimulatorServer()))
    except KeyboardInterrupt:
        return 0
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return simulator_main(argv)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="simulator")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to simulator YAML config. Defaults to config/simulator.yaml or SIMULATOR_CONFIG_PATH.",
    )
    parser.add_argument(
        "--tui",
        action="store_true",
        help="Open an interactive terminal UI for editing configured variables.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(simulator_main())
