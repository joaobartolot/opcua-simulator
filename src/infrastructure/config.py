from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.domain.models import (
    DataType,
    GeneratorSettings,
    RuntimeSettings,
    ServerSettings,
    SimulatorSettings,
    VariableDefinition,
)


DEFAULT_CONFIG_PATH = Path("config/simulator.yaml")


class ServerConfig(BaseModel):
    endpoint: str = "opc.tcp://0.0.0.0:4840"
    namespace_uri: str = "urn:opcua-simulator"
    object_name: str = "Simulator"

    @field_validator("endpoint", "namespace_uri", "object_name")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    def to_domain(self) -> ServerSettings:
        return ServerSettings(
            endpoint=self.endpoint,
            namespace_uri=self.namespace_uri,
            object_name=self.object_name,
        )


class RuntimeConfig(BaseModel):
    update_interval_ms: int = 1000

    @field_validator("update_interval_ms")
    @classmethod
    def validate_update_interval(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("update_interval_ms must be greater than zero")
        return value

    def to_domain(self) -> RuntimeSettings:
        return RuntimeSettings(update_interval_ms=self.update_interval_ms)


class GeneratorConfig(BaseModel):
    kind: str = "sine"
    amplitude: float
    period_ticks: int

    @field_validator("kind")
    @classmethod
    def normalize_kind(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized != "sine":
            raise ValueError("only sine generators are supported")
        return normalized

    def to_domain(self) -> GeneratorSettings:
        return GeneratorSettings(
            kind=self.kind,
            amplitude=self.amplitude,
            period_ticks=self.period_ticks,
        )


class VariableConfig(BaseModel):
    name: str
    node_id: str | None = None
    data_type: DataType = DataType.FLOAT
    default: Any
    unit: str | None = None
    writable: bool = True
    generator: GeneratorConfig | None = None

    @field_validator("name")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    @field_validator("node_id", "unit")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    def to_domain(self, node_id_template: str) -> VariableDefinition:
        node_id = self.node_id or node_id_template.format(name=self.name)
        return VariableDefinition(
            name=self.name,
            node_id=node_id,
            data_type=self.data_type,
            default=self.default,
            unit=self.unit,
            writable=self.writable,
            generator=self.generator.to_domain() if self.generator else None,
        )


class SimulatorConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    node_id_template: str = "ns=2;s={name}"
    variables: list[VariableConfig] = Field(default_factory=list)

    @field_validator("node_id_template")
    @classmethod
    def validate_node_id_template(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("node_id_template must not be empty")
        if "{name}" not in stripped:
            raise ValueError("node_id_template must contain {name}")
        return stripped

    @model_validator(mode="after")
    def validate_domain(self) -> "SimulatorConfig":
        self.to_domain()
        return self

    def to_domain(self) -> SimulatorSettings:
        return SimulatorSettings(
            server=self.server.to_domain(),
            runtime=self.runtime.to_domain(),
            variables=tuple(
                variable.to_domain(self.node_id_template)
                for variable in self.variables
            ),
        )


class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    simulator_config_path: Path = DEFAULT_CONFIG_PATH
    log_level: str | None = None


def load_settings(config_path: str | Path | None = None) -> SimulatorSettings:
    env_settings = EnvSettings()
    resolved_config_path = Path(config_path or env_settings.simulator_config_path)
    data = _load_yaml_mapping(resolved_config_path)
    return SimulatorConfig.model_validate(data).to_domain()


def _load_yaml_mapping(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"simulator config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as config_file:
        data = yaml.safe_load(config_file) or {}

    if not isinstance(data, dict):
        raise ValidationError.from_exception_data(
            "SimulatorConfig",
            [
                {
                    "type": "dict_type",
                    "loc": ("config",),
                    "input": data,
                }
            ],
        )

    return data
