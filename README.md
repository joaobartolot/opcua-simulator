# OPC UA Simulator

## Overview

This project is a standalone OPC UA simulator for local development, integration testing, and manual testing.

It is responsible for:

- Serving OPC UA variables on a local endpoint
- Generating deterministic test values
- Exposing stable node ids for configured variables
- Providing a browser UI for manual value changes
- Supporting manual value changes through an optional terminal UI
- Running locally or in Docker

The simulator should stay independent from any single product, service, or deployment.

---

## Responsibilities

- Start an OPC UA server
- Register configured variables
- Publish variable values through OPC UA
- Update generated values on a fixed interval
- Support predictable manual overrides when enabled
- Shut down cleanly on interruption

---

## Key Principles

- **Product-neutral**: useful across projects and test environments
- **Deterministic**: repeatable values by default
- **Simple to run**: local and Docker workflows should be straightforward
- **Stable node ids**: client tests should not break unexpectedly
- **Low resource usage**: suitable for local development and CI-style smoke tests

---

## Tech Stack

- Python 3.14
- Poetry
- OPC UA server: `asyncua`
- Web API: FastAPI
- Frontend: React, TypeScript, Vite, Tailwind CSS
- YAML configuration
- pytest
- Docker / Docker Compose

---

## Project Structure

```text
opcua-simulator/
├── src/
│   ├── main.py
│   ├── config/
│   │   └── settings.py
│   ├── domain/
│   │   └── models.py
│   ├── application/
│   │   └── simulator.py
│   ├── infrastructure/
│   │   ├── opcua_server.py
│   │   └── logger.py
│   └── dev/
│       └── simulator_tui.py
├── config/
│   └── simulator.yaml
├── tests/
├── pyproject.toml
├── Dockerfile
├── compose.yaml
├── AGENTS.md
└── README.md
```

This structure is the intended shape for the standalone project. Keep implementation changes aligned with `AGENTS.md`.

---

## Configuration

Simulator configuration should live in `config/simulator.yaml`.

Environment variables are reserved for deployment overrides and secrets if secrets are ever introduced.

Supported environment overrides:

- `SIMULATOR_CONFIG_PATH`
- `PUBLIC_WEB_URL`
- `LOG_LEVEL`

Configuration areas:

- OPC UA endpoint, defaulting to `opc.tcp://0.0.0.0:4840`
- namespace URI
- variable definitions
- update interval
- value generation settings

Example:

```yaml
server:
  endpoint: opc.tcp://0.0.0.0:4840
  namespace_uri: urn:opcua-simulator
  object_name: Simulator

node_id_template: ns=2;s={name}

runtime:
  update_interval_ms: 1000

variables:
  - name: thermometer
    data_type: float
    default: 22.0
    unit: celsius
    writable: true

  - name: pump_running
    data_type: boolean
    default: false
    writable: true
```

Variables use the top-level `node_id_template` by default. Add `node_id` only when a tag needs a different address:

```yaml
variables:
  - name: external_sensor
    node_id: ns=4;s=Device.Custom.Sensor
    data_type: float
    default: 0.0
```

Supported `data_type` values:

- `boolean` accepts `true`, `false`, `1`, or `0`
- `int`
- `float`
- `string`

Defaults stay static unless a numeric variable explicitly configures a deterministic generator:

```yaml
generator:
  kind: sine
  amplitude: 2.0
  period_ticks: 10
```

---

## Running

Install dependencies:

```bash
poetry install
```

Run the simulator:

```bash
poetry run simulator
```

Run the simulator with the web UI/API:

```bash
poetry run simulator-web
```

The web UI is available at:

```text
http://localhost:8080
```

Run with an alternate config:

```bash
poetry run simulator -- --config config/simulator.yaml
```

Run the simulator with the optional terminal UI:

```bash
poetry run simulator -- --tui
```

The default local endpoint should be:

```text
opc.tcp://0.0.0.0:4840
```

---

## Docker

```bash
docker compose up --build
```

Compose starts the OPC UA simulator and web UI in one container.

- Web UI/API: `http://localhost:8080`
- OPC UA endpoint: `opc.tcp://localhost:4840`

To scan the startup QR code from a phone, set the public URL to your computer's LAN address:

```bash
PUBLIC_WEB_URL=http://<your-computer-lan-ip>:8080 docker compose up --build
```

The service prints an ASCII QR code for `PUBLIC_WEB_URL` during startup, and the web UI also shows the same QR code.

The web UI can add temporary runtime tags. These tags are exposed through OPC UA immediately, but they are not persisted to `config/simulator.yaml`; restarting the simulator returns to the configured tags only.

---

## Testing

```bash
poetry run pytest
```

Prefer behavior-focused tests for:

- configuration loading
- variable validation
- deterministic value generation
- OPC UA client smoke reads
- clean startup and shutdown behavior

---

## Notes

Keep this project small and predictable.

Avoid coupling the simulator to external services, publishing, persistence, or product-specific workflows unless that scope is explicitly approved.
