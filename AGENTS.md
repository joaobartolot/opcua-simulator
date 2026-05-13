# AGENTS.md

## Purpose

Defines how AI agents must operate in this repository.

Follow these rules strictly. Do not improvise outside them.

---

## Architecture Rules

The simulator follows a layered architecture:

domain -> application -> infrastructure

### Domain

- Pure simulator models and state only
- No external dependencies
- No framework usage
- Represents configured variables, generated values, and simulator state

### Application

- Contains simulator use cases and control flow
- Orchestrates startup, ticking, value updates, and shutdown
- No direct infrastructure logic

### Infrastructure

- Handles external integrations:
  - OPC UA server
  - Configuration loading
  - Logging
  - CLI and optional terminal UI adapters

---

## Project Structure

- `src/domain/` -> simulator models and state
- `src/application/` -> simulator use cases and runtime flow
- `src/infrastructure/` -> OPC UA, configuration, logging, and adapters
- `src/dev/` -> development-only tools, if needed
- `config/` -> simulator configuration
- `tests/` -> behavior tests

Do NOT:

- Move logic between layers incorrectly
- Add external service, publishing, or persistence responsibilities without explicit approval
- Create new top-level folders without strong justification

---

## Simulator Behavior

The simulator serves OPC UA variables for local development, integration tests, and manual testing.

Rules:

- Expose stable node ids for configured variables
- Keep generated values deterministic unless randomness is explicitly requested
- Make defaults useful for local execution
- Keep manual overrides predictable and visible when a UI is present
- Shut down cleanly on interruption

Prefer:

- repeatable test data over realistic but unstable data
- explicit configuration over hidden behavior
- simple control flow over clever automation

---

## Reliability Rules

This is a test and development service. Predictability is more important than feature breadth.

The agent must ensure:

- The OPC UA server starts with a clear endpoint
- Startup failures are reported clearly
- Invalid variable configuration fails early
- Duplicate variable names or node ids are rejected
- Runtime interruptions are handled gracefully

Do NOT:

- hide OPC UA server errors
- silently change configured node ids
- introduce background behavior that cannot be tested

---

## Configuration Rules

- Primary config: `config/simulator.yaml`
- `.env` is ONLY for:
  - environment overrides
  - secrets, if any are introduced later
  - deployment-specific values

Do NOT:

- place simulator domain configuration only in `.env`
- duplicate configuration sources
- hard-code project-specific machine or product names

---

## Implementation Rules

- Prefer consistency with existing code over new patterns
- Do NOT introduce new frameworks or libraries without approval
- Keep logic deterministic and predictable
- Avoid unnecessary abstractions
- Keep the simulator independent from any single product or deployment

Default behavior:

- simple
- explicit
- maintainable
- easy to run locally

---

## Testing Rules

All new behavior must be testable.

Prefer unit tests for:

- configuration loading
- simulator state and variable validation
- generated value behavior
- CLI command routing
- OPC UA server adapters

Prefer integration tests for:

- reading exposed variables through an OPC UA client
- startup and clean shutdown behavior

Tests must focus on behavior, not implementation details.

---

## Common Tasks

### Add Feature

1. Update domain model or configuration schema, if needed
2. Implement simulator behavior in the application layer
3. Integrate via infrastructure adapters
4. Add or update tests
5. Update README usage when commands or config change

---

### Fix Bug

1. Reproduce issue
2. Identify root cause
3. Fix root cause, not symptom
4. Ensure no regression

---

## Self-Validation Rule

Before marking any task as complete, the agent must review its own changes against this file.

Audit scope:

- Check implemented or partially implemented work against this file.
- Do not report unstarted planned capabilities as violations only because they are absent.
- Report a missing capability when the user explicitly asks for feature completeness, when current code or docs claim it exists, or when partial work creates misleading or broken behavior.

The agent must validate:

- architecture rules
- layer boundaries
- simulator behavior
- configuration correctness
- test impact
- product-neutral wording

The agent must explicitly check for:

- architecture drift
- simulator logic in the wrong layer
- hidden coupling to a specific product or deployment
- unstable generated values without a reason
- missing validation for user-facing configuration
- unnecessary complexity

If violations are found, the agent must fix them before completion.

---

## Pre-Commit Review Rule

The agent is allowed to create commits, but only after performing a strict final review.

Before committing, the agent must:

1. Re-run Self-Validation checks

2. Confirm that:
   - the implementation matches the requested scope
   - AGENTS.md rules are respected
   - no architecture violations exist
   - no unintended structural changes were introduced
   - no unnecessary abstractions or complexity were added
   - simulator behavior remains deterministic and product-neutral
   - relevant tests were added or updated when applicable

3. Verify that the commit is safe:
   - no partial implementations
   - no broken flows
   - no obvious runtime risks

---

### Commit Requirements

Every commit created by the agent must include:

- a clear and descriptive message
- a summary of what was implemented
- any known limitations or deferred work
- any risks that were identified but not addressed

---

### Forbidden Behavior

The agent must NOT:

- commit incomplete or experimental code
- commit changes that violate AGENTS.md rules
- introduce architectural changes silently
- include unrelated changes in the same commit

---

### Safety Rule

If the agent is uncertain about:

- correctness
- architecture decisions
- reliability impact
- simulator scope

It must STOP and ask for clarification instead of committing.
