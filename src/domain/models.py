import math
import re
import threading
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


VARIABLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class DataType(StrEnum):
    BOOLEAN = "boolean"
    INT = "int"
    FLOAT = "float"
    STRING = "string"


@dataclass(frozen=True)
class ServerSettings:
    endpoint: str = "opc.tcp://0.0.0.0:4840"
    namespace_uri: str = "urn:opcua-simulator"
    object_name: str = "Simulator"

    def __post_init__(self) -> None:
        if not self.endpoint.strip():
            raise ValueError("server endpoint must not be empty")
        if not self.namespace_uri.strip():
            raise ValueError("server namespace_uri must not be empty")
        if not self.object_name.strip():
            raise ValueError("server object_name must not be empty")


@dataclass(frozen=True)
class RuntimeSettings:
    update_interval_ms: int = 1000

    def __post_init__(self) -> None:
        if self.update_interval_ms <= 0:
            raise ValueError("runtime update_interval_ms must be greater than zero")


@dataclass(frozen=True)
class GeneratorSettings:
    kind: str
    amplitude: float
    period_ticks: int

    def __post_init__(self) -> None:
        if self.kind != "sine":
            raise ValueError("only sine generators are supported")
        if self.period_ticks <= 0:
            raise ValueError("generator period_ticks must be greater than zero")


@dataclass(frozen=True)
class VariableDefinition:
    name: str
    node_id: str
    data_type: DataType
    default: bool | int | float | str
    unit: str | None = None
    writable: bool = True
    generator: GeneratorSettings | None = None

    def __post_init__(self) -> None:
        name = self.name.strip()
        node_id = self.node_id.strip()
        if not VARIABLE_NAME_PATTERN.fullmatch(name):
            raise ValueError(
                "variable name must start with a letter or underscore and contain only letters, numbers, or underscores"
            )
        if not node_id:
            raise ValueError("variable node_id must not be empty")
        if self.generator is not None and self.data_type not in {DataType.INT, DataType.FLOAT}:
            raise ValueError("generators are only supported for int and float variables")
        coerced_default = coerce_value(self.default, self.data_type)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "node_id", node_id)
        object.__setattr__(self, "default", coerced_default)
        if self.unit is not None:
            object.__setattr__(self, "unit", self.unit.strip() or None)


@dataclass(frozen=True)
class SimulatorSettings:
    server: ServerSettings
    runtime: RuntimeSettings
    variables: tuple[VariableDefinition, ...]

    def __post_init__(self) -> None:
        if not self.variables:
            raise ValueError("at least one simulator variable must be configured")
        _reject_duplicates("variable name", (variable.name for variable in self.variables))
        _reject_duplicates("variable node_id", (variable.node_id for variable in self.variables))


@dataclass
class SimulatorVariable:
    definition: VariableDefinition
    value: bool | int | float | str
    auto_update: bool

    @property
    def name(self) -> str:
        return self.definition.name

    @property
    def node_id(self) -> str:
        return self.definition.node_id

    @property
    def data_type(self) -> DataType:
        return self.definition.data_type

    @property
    def unit(self) -> str | None:
        return self.definition.unit


class SimulatorState:
    """Thread-safe runtime values for configured simulator variables."""

    def __init__(self, settings: SimulatorSettings) -> None:
        self._lock = threading.RLock()
        self._variables = {
            variable.name: SimulatorVariable(
                definition=variable,
                value=variable.default,
                auto_update=variable.generator is not None,
            )
            for variable in settings.variables
        }

    def list_variables(self) -> list[SimulatorVariable]:
        with self._lock:
            return [
                SimulatorVariable(
                    definition=variable.definition,
                    value=variable.value,
                    auto_update=variable.auto_update,
                )
                for variable in sorted(self._variables.values(), key=lambda item: item.name)
            ]

    def get_variable(self, name: str) -> SimulatorVariable:
        with self._lock:
            variable = self._variables[name]
            return SimulatorVariable(variable.definition, variable.value, variable.auto_update)

    def add_variable(self, definition: VariableDefinition) -> SimulatorVariable:
        with self._lock:
            if definition.name in self._variables:
                raise ValueError(f"duplicate variable name: {definition.name}")
            if any(
                variable.node_id == definition.node_id
                for variable in self._variables.values()
            ):
                raise ValueError(f"duplicate variable node_id: {definition.node_id}")

            variable = SimulatorVariable(
                definition=definition,
                value=definition.default,
                auto_update=definition.generator is not None,
            )
            self._variables[definition.name] = variable
            return SimulatorVariable(variable.definition, variable.value, variable.auto_update)

    def set_value(
        self,
        name: str,
        value: Any,
        *,
        auto_update: bool = False,
    ) -> None:
        with self._lock:
            variable = self._variables[name]
            variable.value = coerce_value(value, variable.data_type)
            variable.auto_update = auto_update

    def toggle_auto_update(self, name: str) -> None:
        variable = self.get_variable(name)
        self.set_auto_update(name, not variable.auto_update)

    def set_auto_update(self, name: str, enabled: bool) -> None:
        with self._lock:
            variable = self._variables[name]
            if variable.definition.generator is None:
                raise ValueError(f"variable has no generator: {name}")
            variable.auto_update = enabled

    def advance(self, tick: int) -> None:
        with self._lock:
            for variable in self._variables.values():
                if variable.auto_update and variable.definition.generator is not None:
                    variable.value = generated_value(variable.definition, tick)


def generated_value(definition: VariableDefinition, tick: int) -> int | float:
    generator = definition.generator
    if generator is None:
        raise ValueError(f"variable has no generator: {definition.name}")

    angle = (tick / generator.period_ticks) * math.tau
    raw_value = float(definition.default) + math.sin(angle) * generator.amplitude
    if definition.data_type == DataType.INT:
        return int(round(raw_value))
    return round(raw_value, 3)


def coerce_value(value: Any, data_type: DataType) -> bool | int | float | str:
    if data_type == DataType.BOOLEAN:
        return _coerce_boolean(value)
    if data_type == DataType.INT:
        return _coerce_int(value)
    if data_type == DataType.FLOAT:
        return _coerce_float(value)
    if data_type == DataType.STRING:
        if value is None:
            raise ValueError("string value must not be null")
        return str(value)
    raise ValueError(f"unsupported data type: {data_type}")


def _coerce_boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1"}:
            return True
        if normalized in {"false", "0"}:
            return False
    raise ValueError("boolean value must be true, false, 1, or 0")


def _coerce_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("int value must not be boolean")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if re.fullmatch(r"[-+]?\d+", stripped):
            return int(stripped)
    raise ValueError("int value must be an integer")


def _coerce_float(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("float value must not be boolean")
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("float value must be numeric") from error


def _reject_duplicates(label: str, values: Any) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if duplicates:
        duplicate_text = ", ".join(sorted(duplicates))
        raise ValueError(f"duplicate {label}: {duplicate_text}")
