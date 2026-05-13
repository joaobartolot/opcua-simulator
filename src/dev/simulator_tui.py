import asyncio
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
import curses
import logging
import threading

from src.application.simulator import run_simulator_state
from src.domain.models import SimulatorSettings, SimulatorState
from src.infrastructure.opcua_server import AsyncuaSimulatorServer


HELP_TEXT = "q/ctrl-c quit | e edit value | space auto for generated tags"
MAX_LOG_LINES = 200


def run_simulator_tui(settings: SimulatorSettings) -> None:
    state = SimulatorState(settings)
    log_buffer = LogBuffer()
    with capture_tui_logs(log_buffer):
        server_thread = SimulatorServerThread(settings, state)
        server_thread.start()
        server_thread.ready.wait(timeout=5)
        try:
            curses.wrapper(_run_tui, state, server_thread, log_buffer)
        except KeyboardInterrupt:
            logging.getLogger(__name__).info("OPC UA simulator TUI stopped")
        finally:
            server_thread.stop()
            server_thread.join(timeout=5)


class SimulatorServerThread(threading.Thread):
    def __init__(self, settings: SimulatorSettings, state: SimulatorState) -> None:
        super().__init__(daemon=True)
        self.settings = settings
        self.state = state
        self.ready = threading.Event()
        self.stop_requested = threading.Event()
        self.error: BaseException | None = None

    def run(self) -> None:
        try:
            self.ready.set()
            asyncio.run(
                run_simulator_state(
                    self.settings,
                    self.state,
                    AsyncuaSimulatorServer(),
                    stop_requested=self.stop_requested,
                )
            )
        except BaseException as error:
            self.error = error
            self.ready.set()

    def stop(self) -> None:
        self.stop_requested.set()


@contextmanager
def capture_tui_logs(log_buffer: "LogBuffer") -> Iterator[None]:
    root_logger = logging.getLogger()
    previous_handlers = root_logger.handlers[:]
    previous_level = root_logger.level
    handler = TuiLogHandler(log_buffer)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO)
    logging.getLogger("asyncua").setLevel(logging.WARNING)
    try:
        yield
    finally:
        root_logger.handlers = previous_handlers
        root_logger.setLevel(previous_level)


class LogBuffer:
    def __init__(self, max_lines: int = MAX_LOG_LINES) -> None:
        self._lock = threading.Lock()
        self._lines: deque[str] = deque(maxlen=max_lines)

    def append(self, line: str) -> None:
        with self._lock:
            self._lines.append(line)

    def tail(self, count: int) -> list[str]:
        with self._lock:
            if count <= 0:
                return []
            return list(self._lines)[-count:]


class TuiLogHandler(logging.Handler):
    def __init__(self, log_buffer: LogBuffer) -> None:
        super().__init__()
        self.log_buffer = log_buffer

    def emit(self, record: logging.LogRecord) -> None:
        self.log_buffer.append(self.format(record))


def _run_tui(
    screen: curses.window,
    state: SimulatorState,
    server_thread: SimulatorServerThread,
    log_buffer: LogBuffer,
) -> None:
    curses.curs_set(0)
    screen.nodelay(True)
    selected_index = 0
    message = f"OPC UA simulator: {server_thread.settings.server.endpoint}"

    while True:
        if server_thread.error is not None:
            message = f"server error: {server_thread.error}"

        variables = state.list_variables()
        selected_index = _clamp_selected_index(selected_index, variables)
        _draw(screen, variables, selected_index, message, log_buffer)

        key = screen.getch()
        if key == -1:
            curses.napms(150)
            continue
        if key in (3, ord("q"), ord("Q")):
            return
        if key == curses.KEY_UP:
            selected_index = max(0, selected_index - 1)
        elif key == curses.KEY_DOWN:
            selected_index = min(len(variables) - 1, selected_index + 1)
        elif key == ord(" ") and variables:
            message = _toggle_auto_update(state, variables[selected_index].name)
        elif key in (ord("e"), ord("E")) and variables:
            message = _edit_variable(screen, state, variables[selected_index].name)


def _draw(
    screen: curses.window,
    variables: list[object],
    selected_index: int,
    message: str,
    log_buffer: LogBuffer,
) -> None:
    screen.erase()
    height, width = screen.getmaxyx()
    variable_rows, log_start = _layout(height)

    _addstr(screen, 0, 0, "OPC UA Simulator", curses.A_BOLD)
    _addstr(screen, 1, 0, HELP_TEXT[: width - 1])
    _addstr(screen, 2, 0, message[: width - 1])
    _addstr(screen, 4, 0, "Name                 Value        Type       Mode       Node ID", curses.A_BOLD)

    for index, variable in enumerate(variables[:variable_rows]):
        mode = "auto" if variable.auto_update else "manual"
        marker = ">" if index == selected_index else " "
        line = (
            f"{marker} "
            f"{variable.name:<20} "
            f"{str(variable.value):<12} "
            f"{variable.data_type.value:<10} "
            f"{mode:<10} "
            f"{variable.node_id}"
        )
        _addstr(screen, 5 + index, 0, line[: width - 1])

    _draw_log_section(screen, log_start, log_buffer)
    screen.refresh()


def _layout(height: int) -> tuple[int, int]:
    log_start = max(8, height // 2)
    variable_rows = max(0, log_start - 6)
    return variable_rows, log_start


def _draw_log_section(screen: curses.window, start_row: int, log_buffer: LogBuffer) -> None:
    height, width = screen.getmaxyx()
    if start_row >= height:
        return
    _addstr(screen, start_row, 0, "Logs", curses.A_BOLD)
    if start_row + 1 < height:
        _addstr(screen, start_row + 1, 0, "-" * (width - 1))
    max_log_rows = max(0, height - start_row - 2)
    for index, line in enumerate(log_buffer.tail(max_log_rows)):
        _addstr(screen, start_row + 2 + index, 0, line[: width - 1])


def _edit_variable(screen: curses.window, state: SimulatorState, name: str) -> str:
    value_text = _prompt(screen, f"value for {name}")
    try:
        state.set_value(name, value_text)
    except ValueError as error:
        return str(error)
    return f"updated {name}"


def _toggle_auto_update(state: SimulatorState, name: str) -> str:
    try:
        state.toggle_auto_update(name)
    except ValueError as error:
        return str(error)
    return f"toggled auto update for {name}"


def _prompt(screen: curses.window, label: str) -> str:
    curses.echo()
    screen.nodelay(False)
    height, width = screen.getmaxyx()
    prompt = f"{label}: "
    screen.move(height - 1, 0)
    screen.clrtoeol()
    _addstr(screen, height - 1, 0, prompt)
    response = screen.getstr(height - 1, len(prompt), width - len(prompt) - 1)
    screen.nodelay(True)
    curses.noecho()
    return response.decode("utf-8").strip()


def _clamp_selected_index(selected_index: int, variables: list[object]) -> int:
    if not variables:
        return 0
    return min(selected_index, len(variables) - 1)


def _addstr(
    screen: curses.window,
    y: int,
    x: int,
    text: str,
    attributes: int = curses.A_NORMAL,
) -> None:
    height, width = screen.getmaxyx()
    if y >= height or x >= width:
        return
    screen.addstr(y, x, text[: max(0, width - x - 1)], attributes)
