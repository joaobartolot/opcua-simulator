import { FormEvent, useEffect, useMemo, useState } from "react";

type DataType = "boolean" | "int" | "float" | "string";
type GeneratorKind = "sine" | "totalizer";

type GeneratorConfig = {
  kind: GeneratorKind;
  amplitude: number | null;
  period_ticks: number | null;
  rate_liters_per_minute: number | null;
  enabled_by: string | null;
};

type SimulatorVariable = {
  name: string;
  node_id: string;
  data_type: DataType;
  value: boolean | number | string;
  unit: string | null;
  writable: boolean;
  auto_update: boolean;
  has_generator: boolean;
  generator: GeneratorConfig | null;
};

type VariablesResponse = {
  variables: SimulatorVariable[];
};

type AccessResponse = {
  public_url: string;
};

type DraftValues = Record<string, string>;
type RowErrors = Record<string, string>;

type NewTagForm = {
  name: string;
  dataType: DataType;
  defaultValue: string;
  unit: string;
  nodeId: string;
  writable: boolean;
  generatorEnabled: boolean;
  generatorKind: GeneratorKind;
  amplitude: string;
  periodTicks: string;
  rateLitersPerMinute: string;
  enabledBy: string;
};

const emptyNewTagForm: NewTagForm = {
  name: "",
  dataType: "float",
  defaultValue: "0",
  unit: "",
  nodeId: "",
  writable: true,
  generatorEnabled: false,
  generatorKind: "sine",
  amplitude: "1",
  periodTicks: "10",
  rateLitersPerMinute: "60",
  enabledBy: ""
};

export function App() {
  const [variables, setVariables] = useState<SimulatorVariable[]>([]);
  const [drafts, setDrafts] = useState<DraftValues>({});
  const [errors, setErrors] = useState<RowErrors>({});
  const [newTag, setNewTag] = useState<NewTagForm>(emptyNewTagForm);
  const [newTagError, setNewTagError] = useState("");
  const [isAddTagOpen, setIsAddTagOpen] = useState(false);
  const [publicUrl, setPublicUrl] = useState("");
  const [connection, setConnection] = useState("connecting");

  useEffect(() => {
    loadVariables();
    loadAccess();

    const events = new EventSource("/api/events");
    events.addEventListener("variables", (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as VariablesResponse;
      setVariables(payload.variables);
      setConnection("live");
    });
    events.onerror = () => {
      setConnection("reconnecting");
      void loadVariables();
    };

    return () => events.close();
  }, []);

  useEffect(() => {
    if (!isAddTagOpen) {
      return;
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        closeAddTagModal();
      }
    }

    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [isAddTagOpen]);

  useEffect(() => {
    setDrafts((current) => {
      const next = { ...current };
      for (const variable of variables) {
        if (!(variable.name in next)) {
          next[variable.name] = formatValue(variable.value);
        }
      }
      return next;
    });
  }, [variables]);

  const sortedVariables = useMemo(
    () => [...variables].sort((left, right) => left.name.localeCompare(right.name)),
    [variables]
  );
  const booleanVariables = useMemo(
    () => sortedVariables.filter((variable) => variable.data_type === "boolean"),
    [sortedVariables]
  );

  async function loadAccess() {
    const response = await fetch("/api/access");
    if (!response.ok) {
      return;
    }
    const payload = (await response.json()) as AccessResponse;
    setPublicUrl(payload.public_url);
  }

  async function loadVariables() {
    const response = await fetch("/api/variables");
    if (!response.ok) {
      setConnection("offline");
      return;
    }
    const payload = (await response.json()) as VariablesResponse;
    setVariables(payload.variables);
    setConnection("online");
  }

  async function saveVariable(event: FormEvent<HTMLFormElement>, variable: SimulatorVariable) {
    event.preventDefault();
    await saveVariableValue(variable, drafts[variable.name] ?? "");
  }

  async function saveVariableValue(variable: SimulatorVariable, draft: string) {
    setErrors((current) => ({ ...current, [variable.name]: "" }));
    const value = valueForApi(variable, draft);

    const response = await fetch(`/api/variables/${encodeURIComponent(variable.name)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value })
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({ detail: "update failed" }));
      setErrors((current) => ({
        ...current,
        [variable.name]: String(payload.detail ?? "update failed")
      }));
      return;
    }

    const updated = (await response.json()) as SimulatorVariable;
    setVariables((current) =>
      current.map((item) => (item.name === updated.name ? updated : item))
    );
    setDrafts((current) => ({ ...current, [updated.name]: formatValue(updated.value) }));
  }

  async function setAuto(variable: SimulatorVariable, enabled: boolean) {
    setErrors((current) => ({ ...current, [variable.name]: "" }));
    const response = await fetch(`/api/variables/${encodeURIComponent(variable.name)}/auto`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled })
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({ detail: "auto update failed" }));
      setErrors((current) => ({
        ...current,
        [variable.name]: String(payload.detail ?? "auto update failed")
      }));
    }
  }

  async function createTag(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNewTagError("");

    const body = {
      name: newTag.name,
      data_type: newTag.dataType,
      default: valueForType(newTag.dataType, newTag.defaultValue),
      node_id: newTag.nodeId.trim() || null,
      unit: newTag.unit.trim() || null,
      writable: newTag.writable,
      generator:
        newTag.generatorEnabled && isNumericType(newTag.dataType)
          ? generatorForApi(newTag)
          : null
    };

    const response = await fetch("/api/variables", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({ detail: "create failed" }));
      setNewTagError(String(payload.detail ?? "create failed"));
      return;
    }

    const created = (await response.json()) as SimulatorVariable;
    setVariables((current) => [...current.filter((item) => item.name !== created.name), created]);
    setDrafts((current) => ({ ...current, [created.name]: formatValue(created.value) }));
    closeAddTagModal();
  }

  function openAddTagModal() {
    setNewTagError("");
    setIsAddTagOpen(true);
  }

  function closeAddTagModal() {
    setIsAddTagOpen(false);
    setNewTag(emptyNewTagForm);
    setNewTagError("");
  }

  return (
    <main className="min-h-screen bg-panel text-ink">
      <div className="mx-auto flex max-w-7xl flex-col gap-5 px-4 py-5 sm:px-6 lg:px-8">
        <header className="flex flex-col justify-between gap-3 border-b border-line pb-4 md:flex-row md:items-end">
          <div>
            <h1 className="text-2xl font-semibold">OPC UA Simulator</h1>
            <p className="mt-1 text-sm text-slate-600">
              Endpoint values and manual overrides
            </p>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <button
              type="button"
              onClick={openAddTagModal}
              className="rounded bg-accent px-3 py-1.5 font-medium text-white"
            >
              Add tag
            </button>
            <span className="rounded border border-line bg-white px-2 py-1 font-mono">
              {connection}
            </span>
            <span className="rounded border border-line bg-white px-2 py-1">
              {variables.length} tags
            </span>
          </div>
        </header>

        <section className="grid gap-4 lg:grid-cols-[1fr_280px]">
          <div className="overflow-hidden rounded-md border border-line bg-white">
            <div className="overflow-x-auto">
              <table className="min-w-full border-collapse text-sm">
                <thead className="bg-slate-100 text-left text-xs uppercase text-slate-600">
                  <tr>
                    <th className="px-3 py-3">Tag</th>
                    <th className="px-3 py-3">Value</th>
                    <th className="px-3 py-3">Type</th>
                    <th className="px-3 py-3">Mode</th>
                    <th className="px-3 py-3">Node ID</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedVariables.map((variable) => (
                    <VariableRow
                      key={variable.name}
                      variable={variable}
                      draft={drafts[variable.name] ?? ""}
                      error={errors[variable.name] ?? ""}
                      onDraftChange={(value) =>
                        setDrafts((current) => ({ ...current, [variable.name]: value }))
                      }
                      onSave={(event) => saveVariable(event, variable)}
                      onQuickSave={(value) => saveVariableValue(variable, value)}
                      onAutoChange={(enabled) => setAuto(variable, enabled)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <aside className="rounded-md border border-line bg-white p-4">
            <h2 className="text-sm font-semibold uppercase text-slate-600">Phone Access</h2>
            <div className="mt-4 flex justify-center rounded border border-line bg-white p-3">
              <img src="/api/qr.svg" alt="QR code for web UI" className="h-48 w-48" />
            </div>
            <p className="mt-3 break-all rounded border border-line bg-slate-50 p-2 font-mono text-xs">
              {publicUrl || "loading"}
            </p>
          </aside>
        </section>
      </div>
      {isAddTagOpen ? (
        <AddTagModal
          form={newTag}
          error={newTagError}
          booleanVariables={booleanVariables}
          onChange={(patch) => setNewTag((current) => ({ ...current, ...patch }))}
          onSubmit={createTag}
          onClose={closeAddTagModal}
        />
      ) : null}
    </main>
  );
}

function AddTagModal({
  form,
  error,
  booleanVariables,
  onChange,
  onSubmit,
  onClose
}: {
  form: NewTagForm;
  error: string;
  booleanVariables: SimulatorVariable[];
  onChange: (patch: Partial<NewTagForm>) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onClose: () => void;
}) {
  const nodePreview = form.nodeId.trim() || `ns=2;s=${form.name || "<name>"}`;
  const generatorAllowed = isNumericType(form.dataType);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 px-4 py-6"
      onClick={onClose}
    >
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-tag-title"
        className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-md border border-line bg-white shadow-xl"
        onSubmit={onSubmit}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <div>
            <h2 id="add-tag-title" className="text-base font-semibold">
              Add tag
            </h2>
            <p className="mt-1 text-xs text-slate-600">
              Temporary runtime tag, not saved to config
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-line px-2 py-1 text-sm"
          >
            Close
          </button>
        </div>

        <div className="grid gap-3 p-4 md:grid-cols-2">
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
            Name
            <input
              value={form.name}
              onChange={(event) => onChange({ name: event.target.value })}
              className="h-9 rounded border border-line bg-white px-2 text-sm text-ink"
              placeholder="runtime_sensor"
            />
          </label>

          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
            Type
            <select
              value={form.dataType}
              onChange={(event) => {
                const dataType = event.target.value as DataType;
                onChange({
                  dataType,
                  defaultValue: dataType === "boolean" ? "0" : dataType === "string" ? "" : "0",
                  generatorEnabled: isNumericType(dataType) ? form.generatorEnabled : false
                });
              }}
              className="h-9 rounded border border-line bg-white px-2 text-sm text-ink"
            >
              <option value="boolean">boolean</option>
              <option value="int">int</option>
              <option value="float">float</option>
              <option value="string">string</option>
            </select>
          </label>

          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
            Default
            {form.dataType === "boolean" ? (
              <select
                value={form.defaultValue}
                onChange={(event) => onChange({ defaultValue: event.target.value })}
                className="h-9 rounded border border-line bg-white px-2 text-sm text-ink"
              >
                <option value="0">0 / false</option>
                <option value="1">1 / true</option>
              </select>
            ) : (
              <input
                value={form.defaultValue}
                onChange={(event) => onChange({ defaultValue: event.target.value })}
                type={form.dataType === "string" ? "text" : "number"}
                step={form.dataType === "int" ? "1" : "any"}
                className="h-9 rounded border border-line bg-white px-2 text-sm text-ink"
              />
            )}
          </label>

          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
            Unit
            <input
              value={form.unit}
              onChange={(event) => onChange({ unit: event.target.value })}
              className="h-9 rounded border border-line bg-white px-2 text-sm text-ink"
              placeholder="optional"
            />
          </label>

          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600 md:col-span-2">
            Node ID override
            <input
              value={form.nodeId}
              onChange={(event) => onChange({ nodeId: event.target.value })}
              className="h-9 rounded border border-line bg-white px-2 font-mono text-sm text-ink"
              placeholder={nodePreview}
            />
          </label>

          <div className="flex flex-wrap items-center gap-3 text-sm md:col-span-2">
            <label className="inline-flex items-center gap-2">
              <input
                type="checkbox"
                checked={form.writable}
                onChange={(event) => onChange({ writable: event.target.checked })}
              />
              Writable
            </label>
            <label className="inline-flex items-center gap-2">
              <input
                type="checkbox"
                checked={form.generatorEnabled}
                disabled={!generatorAllowed}
                onChange={(event) => onChange({ generatorEnabled: event.target.checked })}
              />
              Auto generator
            </label>
            <code className="rounded border border-line bg-slate-50 px-2 py-1 text-xs">
              {nodePreview}
            </code>
          </div>

          <input
            value={form.amplitude}
            disabled={!form.generatorEnabled || !generatorAllowed || form.generatorKind !== "sine"}
            onChange={(event) => onChange({ amplitude: event.target.value })}
            type="number"
            step="any"
            className="h-9 rounded border border-line bg-white px-2 text-sm disabled:bg-slate-100"
            placeholder="amplitude"
          />
          <input
            value={form.periodTicks}
            disabled={!form.generatorEnabled || !generatorAllowed || form.generatorKind !== "sine"}
            onChange={(event) => onChange({ periodTicks: event.target.value })}
            type="number"
            step="1"
            min="1"
            className="h-9 rounded border border-line bg-white px-2 text-sm disabled:bg-slate-100"
            placeholder="period"
          />

          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
            Generator type
            <select
              value={form.generatorKind}
              disabled={!form.generatorEnabled || !generatorAllowed}
              onChange={(event) =>
                onChange({ generatorKind: event.target.value as GeneratorKind })
              }
              className="h-9 rounded border border-line bg-white px-2 text-sm text-ink disabled:bg-slate-100"
            >
              <option value="sine">sine</option>
              <option value="totalizer">totalizer</option>
            </select>
          </label>

          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
            Rate liters/min
            <input
              value={form.rateLitersPerMinute}
              disabled={
                !form.generatorEnabled || !generatorAllowed || form.generatorKind !== "totalizer"
              }
              onChange={(event) => onChange({ rateLitersPerMinute: event.target.value })}
              type="number"
              step="any"
              min="0"
              className="h-9 rounded border border-line bg-white px-2 text-sm disabled:bg-slate-100"
            />
          </label>

          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600 md:col-span-2">
            Enabled by
            <select
              value={form.enabledBy}
              disabled={
                !form.generatorEnabled || !generatorAllowed || form.generatorKind !== "totalizer"
              }
              onChange={(event) => onChange({ enabledBy: event.target.value })}
              className="h-9 rounded border border-line bg-white px-2 text-sm text-ink disabled:bg-slate-100"
            >
              <option value="">always enabled</option>
              {booleanVariables.map((variable) => (
                <option key={variable.name} value={variable.name}>
                  {variable.name}
                </option>
              ))}
            </select>
          </label>

          {error ? <div className="text-sm text-red-700 md:col-span-2">{error}</div> : null}
        </div>

        <div className="flex justify-end gap-2 border-t border-line bg-slate-50 px-4 py-3">
          <button
            type="button"
            onClick={onClose}
            className="h-9 rounded border border-line bg-white px-4 text-sm"
          >
            Cancel
          </button>
          <button
            type="submit"
            className="h-9 rounded bg-accent px-4 text-sm font-medium text-white"
          >
            Create tag
          </button>
        </div>
      </form>
    </div>
  );
}

function VariableRow({
  variable,
  draft,
  error,
  onDraftChange,
  onSave,
  onQuickSave,
  onAutoChange
}: {
  variable: SimulatorVariable;
  draft: string;
  error: string;
  onDraftChange: (value: string) => void;
  onSave: (event: FormEvent<HTMLFormElement>) => void;
  onQuickSave: (value: string) => void;
  onAutoChange: (enabled: boolean) => void;
}) {
  return (
    <tr className="border-t border-line align-top">
      <td className="px-3 py-3">
        <div className="font-medium">{variable.name}</div>
        {variable.unit ? <div className="text-xs text-slate-500">{variable.unit}</div> : null}
      </td>
      <td className="px-3 py-3">
        <form className="flex min-w-56 flex-col gap-2" onSubmit={onSave}>
          <ValueEditor
            variable={variable}
            draft={draft}
            onDraftChange={onDraftChange}
            onQuickSave={onQuickSave}
          />
          {error ? <div className="text-xs text-red-700">{error}</div> : null}
        </form>
      </td>
      <td className="px-3 py-3">
        <span className="rounded border border-line bg-slate-50 px-2 py-1 font-mono text-xs">
          {variable.data_type}
        </span>
      </td>
      <td className="px-3 py-3">
        <div className="flex flex-col gap-2">
          <span className="text-xs">{variable.auto_update ? "auto" : "manual"}</span>
          {variable.generator ? (
            <span className="text-xs text-slate-500">{generatorLabel(variable.generator)}</span>
          ) : null}
          <button
            type="button"
            disabled={!variable.has_generator}
            onClick={() => onAutoChange(!variable.auto_update)}
            className="w-24 rounded border border-line px-2 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-40"
          >
            {variable.auto_update ? "Manual" : "Auto"}
          </button>
        </div>
      </td>
      <td className="px-3 py-3">
        <code className="break-all text-xs text-slate-700">{variable.node_id}</code>
      </td>
    </tr>
  );
}

function ValueEditor({
  variable,
  draft,
  onDraftChange,
  onQuickSave
}: {
  variable: SimulatorVariable;
  draft: string;
  onDraftChange: (value: string) => void;
  onQuickSave: (value: string) => void;
}) {
  if (variable.data_type === "boolean") {
    return (
      <div className="inline-flex w-28 overflow-hidden rounded border border-line">
        {["0", "1"].map((value) => (
          <button
            key={value}
            type="button"
            disabled={!variable.writable}
            onClick={() => {
              onDraftChange(value);
              onQuickSave(value);
            }}
            className={`flex-1 px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-40 ${
              draft === value ? "bg-accent text-white" : "bg-white"
            }`}
          >
            {value}
          </button>
        ))}
      </div>
    );
  }

  return (
    <div className="flex gap-2">
      <input
        value={draft}
        disabled={!variable.writable}
        type={variable.data_type === "string" ? "text" : "number"}
        step={variable.data_type === "int" ? "1" : "any"}
        onChange={(event) => onDraftChange(event.target.value)}
        className="h-9 min-w-0 flex-1 rounded border border-line px-2 text-sm disabled:bg-slate-100"
      />
      <button
        type="submit"
        disabled={!variable.writable}
        className="h-9 rounded bg-accent px-3 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-400"
      >
        Set
      </button>
    </div>
  );
}

function formatValue(value: boolean | number | string): string {
  if (typeof value === "boolean") {
    return value ? "1" : "0";
  }
  return String(value);
}

function valueForApi(variable: SimulatorVariable, draft: string): boolean | number | string {
  return valueForType(variable.data_type, draft);
}

function valueForType(dataType: DataType, draft: string): boolean | number | string {
  if (dataType === "boolean") {
    return draft === "1";
  }
  if (dataType === "int") {
    return Number.parseInt(draft, 10);
  }
  if (dataType === "float") {
    return Number.parseFloat(draft);
  }
  return draft;
}

function isNumericType(dataType: DataType): boolean {
  return dataType === "int" || dataType === "float";
}

function generatorForApi(form: NewTagForm) {
  if (form.generatorKind === "totalizer") {
    return {
      kind: "totalizer",
      rate_liters_per_minute: Number.parseFloat(form.rateLitersPerMinute),
      enabled_by: form.enabledBy || null
    };
  }

  return {
    kind: "sine",
    amplitude: Number.parseFloat(form.amplitude),
    period_ticks: Number.parseInt(form.periodTicks, 10)
  };
}

function generatorLabel(generator: GeneratorConfig): string {
  if (generator.kind === "totalizer") {
    const rate = generator.rate_liters_per_minute ?? 0;
    return generator.enabled_by ? `${rate} L/min by ${generator.enabled_by}` : `${rate} L/min`;
  }
  return "sine";
}
