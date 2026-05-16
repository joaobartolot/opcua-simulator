import argparse
import asyncio
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import uvicorn

from src.application.simulator import run_simulator
from src.dev.simulator_tui import run_simulator_tui
from src.domain.models import SimulatorSettings
from src.infrastructure.config import load_settings
from src.infrastructure.logger import configure_logging
from src.infrastructure.opcua_server import AsyncuaSimulatorServer
from src.infrastructure.web import create_app


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


def web_main(
    argv: Sequence[str] | None = None,
    *,
    settings_loader: SettingsLoader = load_settings,
    uvicorn_runner: Callable[..., Any] = uvicorn.run,
) -> int:
    args = _parse_web_args(argv)
    log_level = os.getenv("LOG_LEVEL", "INFO")
    configure_logging(log_level)
    settings = settings_loader(args.config)
    if _endpoint_port(settings.server.endpoint) == args.port:
        print(
            "web port conflicts with the OPC UA endpoint port. "
            f"Use different ports for HTTP ({args.port}) and OPC UA "
            f"({settings.server.endpoint}).",
            file=sys.stderr,
        )
        return 2

    app = create_app(
        settings,
        static_dir=args.static_dir,
        public_web_url=os.getenv("PUBLIC_WEB_URL"),
    )
    uvicorn_runner(app, host=args.host, port=args.port, log_config=None)
    return 0


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


def _parse_web_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="simulator-web")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to simulator YAML config. Defaults to config/simulator.yaml or SIMULATOR_CONFIG_PATH.",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("SIMULATOR_WEB_HOST", "0.0.0.0"),
        help="HTTP host for the web UI and API.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("SIMULATOR_WEB_PORT", "8000")),
        help="HTTP port for the web UI and API.",
    )
    parser.add_argument(
        "--static-dir",
        type=Path,
        default=Path(os.getenv("SIMULATOR_WEB_STATIC_DIR", "frontend/dist")),
        help="Directory containing built React assets.",
    )
    return parser.parse_args(argv)


def _endpoint_port(endpoint: str) -> int | None:
    parsed = urlparse(endpoint)
    try:
        return parsed.port
    except ValueError:
        return None


if __name__ == "__main__":
    sys.exit(simulator_main())
