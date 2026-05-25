import { FormEvent, MouseEvent, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

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

type BrowserDefaultsResponse = {
  endpoint: string;
  max_depth: number;
  max_nodes: number;
};

type BrowserNode = {
  node_id: string;
  browse_name: string;
  display_name: string;
  node_class: string;
  path: string;
  relative_path: string;
  has_children: boolean;
  child_count: number | null;
  value: unknown | null;
  value_error: string | null;
  browse_error: string | null;
  children: BrowserNode[];
};

type BrowseResponse = {
  node: BrowserNode;
  truncated: boolean;
  visited_nodes: number;
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
  const [path, setPath] = useState(window.location.pathname);

  function navigate(nextPath: string) {
    window.history.pushState(null, "", nextPath);
    setPath(nextPath);
  }

  useEffect(() => {
    function onPopState() {
      setPath(window.location.pathname);
    }

    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  if (path === "/browser") {
    return <BrowserPage onNavigate={navigate} />;
  }

  return <SimulatorPage onNavigate={navigate} />;
}

function AppFrame({
  activePage,
  onNavigate,
  children
}: {
  activePage: "simulator" | "browser";
  onNavigate: (path: string) => void;
  children: ReactNode;
}) {
  return (
    <main className="min-h-screen bg-panel text-ink">
      <div className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-3 sm:px-6 md:flex-row md:items-center md:justify-between lg:px-8">
          <div>
            <div className="text-base font-semibold">OPC UA Simulator</div>
            <div className="text-xs text-slate-500">Simulator controls and OPC UA browser</div>
          </div>
          <nav className="flex w-full items-center gap-5 border-t border-line pt-3 text-sm md:w-auto md:border-t-0 md:pt-0">
            <button
              type="button"
              onClick={() => onNavigate("/")}
              className={`border-b-2 px-0.5 py-1 font-medium ${
                activePage === "simulator"
                  ? "border-accent text-ink"
                  : "border-transparent text-slate-600 hover:text-ink"
              }`}
            >
              Simulator
            </button>
            <button
              type="button"
              onClick={() => onNavigate("/browser")}
              className={`border-b-2 px-0.5 py-1 font-medium ${
                activePage === "browser"
                  ? "border-accent text-ink"
                  : "border-transparent text-slate-600 hover:text-ink"
              }`}
            >
              Browser
            </button>
          </nav>
        </div>
      </div>
      <div className="mx-auto flex max-w-7xl flex-col gap-5 px-4 py-5 sm:px-6 lg:px-8">
        {children}
      </div>
    </main>
  );
}

function SimulatorPage({ onNavigate }: { onNavigate: (path: string) => void }) {
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
    <AppFrame activePage="simulator" onNavigate={onNavigate}>
      <section className="flex flex-col justify-between gap-3 border-b border-line pb-4 md:flex-row md:items-end">
        <div>
          <h1 className="text-2xl font-semibold">Simulator tags</h1>
          <p className="mt-1 text-sm text-slate-600">
            Endpoint values and manual overrides
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-sm">
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
      </section>

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
    </AppFrame>
  );
}

function BrowserPage({ onNavigate }: { onNavigate: (path: string) => void }) {
  const [endpoint, setEndpoint] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [root, setRoot] = useState<BrowserNode | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [status, setStatus] = useState("not connected");
  const [error, setError] = useState("");
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [limits, setLimits] = useState({ maxDepth: 6, maxNodes: 500 });
  const [menu, setMenu] = useState<{ x: number; y: number; node: BrowserNode } | null>(null);

  const selectedNode = useMemo(
    () => (root && selectedNodeId ? findNode(root, selectedNodeId) : root),
    [root, selectedNodeId]
  );

  useEffect(() => {
    void loadBrowserDefaults();
  }, []);

  useEffect(() => {
    if (!isSettingsOpen) {
      return;
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsSettingsOpen(false);
      }
    }

    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [isSettingsOpen]);

  useEffect(() => {
    function closeMenu() {
      setMenu(null);
    }

    window.addEventListener("click", closeMenu);
    return () => window.removeEventListener("click", closeMenu);
  }, []);

  async function loadBrowserDefaults() {
    const response = await fetch("/api/browser/defaults");
    if (!response.ok) {
      return;
    }
    const payload = (await response.json()) as BrowserDefaultsResponse;
    setEndpoint(payload.endpoint);
    setLimits({ maxDepth: payload.max_depth, maxNodes: payload.max_nodes });
  }

  function connectionBody(node?: BrowserNode) {
    return {
      endpoint,
      username: username.trim() || null,
      password: password || null,
      node_id: node?.node_id ?? null,
      path: node?.path ?? null,
      relative_path: node?.relative_path ?? null
    };
  }

  async function connect() {
    setError("");
    setStatus("connecting");
    const response = await fetch("/api/browser/browse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(connectionBody())
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({ detail: "browse failed" }));
      setStatus("offline");
      setError(String(payload.detail ?? "browse failed"));
      return;
    }

    const payload = (await response.json()) as BrowseResponse;
    setRoot(payload.node);
    setSelectedNodeId(payload.node.node_id);
    setExpanded(new Set([payload.node.node_id]));
    setStatus("connected");
    setIsSettingsOpen(false);
  }

  async function loadChildren(node: BrowserNode) {
    setError("");
    const response = await fetch("/api/browser/browse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(connectionBody(node))
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({ detail: "browse failed" }));
      setError(String(payload.detail ?? "browse failed"));
      return;
    }

    const payload = (await response.json()) as BrowseResponse;
    setRoot((current) => (current ? replaceNode(current, payload.node) : payload.node));
    setExpanded((current) => new Set(current).add(node.node_id));
  }

  async function expandAll() {
    const startNode = selectedNode ?? root;
    if (!startNode) {
      return;
    }

    setError("");
    setStatus("expanding");
    const response = await fetch("/api/browser/expand", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...connectionBody(startNode),
        max_depth: limits.maxDepth,
        max_nodes: limits.maxNodes
      })
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({ detail: "expand failed" }));
      setStatus("connected");
      setError(String(payload.detail ?? "expand failed"));
      return;
    }

    const payload = (await response.json()) as BrowseResponse;
    setRoot((current) => (current ? replaceNode(current, payload.node) : payload.node));
    setExpanded((current) => {
      const next = new Set(current);
      collectExpandableNodeIds(payload.node, next);
      return next;
    });
    setStatus(payload.truncated ? `truncated at ${payload.visited_nodes} nodes` : "connected");
  }

  function toggleNode(node: BrowserNode) {
    setSelectedNodeId(node.node_id);
    if (!node.has_children) {
      return;
    }
    if (expanded.has(node.node_id)) {
      setExpanded((current) => {
        const next = new Set(current);
        next.delete(node.node_id);
        return next;
      });
      return;
    }
    if (node.children.length === 0) {
      void loadChildren(node);
      return;
    }
    setExpanded((current) => new Set(current).add(node.node_id));
  }

  function openContextMenu(event: MouseEvent, node: BrowserNode) {
    event.preventDefault();
    setSelectedNodeId(node.node_id);
    setMenu({ x: event.clientX, y: event.clientY, node });
  }

  async function copyText(value: string) {
    await navigator.clipboard.writeText(value);
    setMenu(null);
  }

  return (
    <AppFrame activePage="browser" onNavigate={onNavigate}>
      <section className="flex flex-col justify-between gap-3 border-b border-line pb-4 md:flex-row md:items-end">
        <div>
          <h1 className="text-2xl font-semibold">OPC UA Browser</h1>
          <p className="mt-1 break-all text-sm text-slate-600">{endpoint || "no endpoint"}</p>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <button
            type="button"
            onClick={() => setIsSettingsOpen(true)}
            className="rounded border border-line bg-white px-3 py-1.5 font-medium"
          >
            Connection
          </button>
          <button
            type="button"
            onClick={expandAll}
            disabled={!root}
            className="rounded bg-accent px-3 py-1.5 font-medium text-white disabled:bg-slate-400"
          >
            Expand all
          </button>
          <span className="rounded border border-line bg-white px-2 py-1 font-mono">
            {status}
          </span>
        </div>
      </section>

        {error ? <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">{error}</div> : null}

        <section className="grid min-h-[70vh] gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div className="overflow-hidden rounded-md border border-line bg-white">
            <div className="border-b border-line bg-slate-100 px-3 py-2 text-xs font-semibold uppercase text-slate-600">
              Address Space
            </div>
            <div className="max-h-[70vh] overflow-auto p-2 text-sm">
              {root ? (
                <BrowserTree
                  node={root}
                  expanded={expanded}
                  selectedNodeId={selectedNodeId}
                  onToggle={toggleNode}
                  onSelect={(node) => setSelectedNodeId(node.node_id)}
                  onContextMenu={openContextMenu}
                  onCopy={copyText}
                />
              ) : (
                <div className="p-6 text-sm text-slate-600">
                  Open Connection and connect to browse the OPC UA address space.
                </div>
              )}
            </div>
          </div>

          <aside className="rounded-md border border-line bg-white p-4">
            <h2 className="text-sm font-semibold uppercase text-slate-600">Selected Node</h2>
            {selectedNode ? (
              <NodeDetails node={selectedNode} onCopy={copyText} />
            ) : (
              <p className="mt-3 text-sm text-slate-600">No node selected.</p>
            )}
          </aside>
        </section>

      {isSettingsOpen ? (
        <BrowserSettingsModal
          endpoint={endpoint}
          username={username}
          password={password}
          onEndpointChange={setEndpoint}
          onUsernameChange={setUsername}
          onPasswordChange={setPassword}
          onConnect={connect}
          onClose={() => setIsSettingsOpen(false)}
        />
      ) : null}
      {menu ? <CopyMenu menu={menu} onCopy={copyText} /> : null}
    </AppFrame>
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

function BrowserTree({
  node,
  expanded,
  selectedNodeId,
  onToggle,
  onSelect,
  onContextMenu,
  onCopy,
  depth = 0
}: {
  node: BrowserNode;
  expanded: Set<string>;
  selectedNodeId: string | null;
  onToggle: (node: BrowserNode) => void;
  onSelect: (node: BrowserNode) => void;
  onContextMenu: (event: MouseEvent, node: BrowserNode) => void;
  onCopy: (value: string) => void;
  depth?: number;
}) {
  const isExpanded = expanded.has(node.node_id);
  const isSelected = selectedNodeId === node.node_id;
  const label = node.display_name || node.browse_name || node.node_id;

  return (
    <div>
      <div
        className={`grid min-h-9 grid-cols-[2rem_minmax(10rem,1fr)_8rem_7rem_5rem] items-center gap-2 rounded px-2 ${
          isSelected ? "bg-teal-50" : "hover:bg-slate-50"
        }`}
        style={{ paddingLeft: `${depth * 18 + 8}px` }}
        onContextMenu={(event) => onContextMenu(event, node)}
      >
        <button
          type="button"
          disabled={!node.has_children}
          onClick={() => onToggle(node)}
          className="h-7 w-7 rounded border border-line text-xs disabled:opacity-30"
          title={isExpanded ? "Collapse" : "Expand"}
        >
          {node.has_children ? (isExpanded ? "-" : "+") : ""}
        </button>
        <button
          type="button"
          onClick={() => onSelect(node)}
          className="min-w-0 text-left"
          title={node.path}
        >
          <span className="block truncate font-medium">{label}</span>
          <span className="block truncate font-mono text-xs text-slate-500">{node.node_id}</span>
        </button>
        <span className="truncate rounded border border-line bg-slate-50 px-2 py-1 font-mono text-xs">
          {node.node_class}
        </span>
        <span className="truncate font-mono text-xs text-slate-700">
          {node.value_error ? "read error" : formatBrowserValue(node.value)}
        </span>
        <button
          type="button"
          onClick={() => onCopy(node.node_id)}
          className="rounded border border-line px-2 py-1 text-xs"
        >
          Copy
        </button>
      </div>
      {isExpanded
        ? node.children.map((child) => (
            <BrowserTree
              key={child.node_id}
              node={child}
              expanded={expanded}
              selectedNodeId={selectedNodeId}
              onToggle={onToggle}
              onSelect={onSelect}
              onContextMenu={onContextMenu}
              onCopy={onCopy}
              depth={depth + 1}
            />
          ))
        : null}
    </div>
  );
}

function NodeDetails({ node, onCopy }: { node: BrowserNode; onCopy: (value: string) => void }) {
  return (
    <div className="mt-4 flex flex-col gap-3 text-sm">
      <DetailRow label="Name" value={node.display_name || node.browse_name || node.node_id} />
      <DetailRow label="Class" value={node.node_class} />
      <DetailRow label="Value" value={node.value_error ? node.value_error : formatBrowserValue(node.value)} />
      <DetailRow label="Children" value={String(node.child_count ?? "unknown")} />
      <CopyField label="Node ID" value={node.node_id} onCopy={onCopy} />
      <CopyField label="Full path" value={node.path} onCopy={onCopy} />
      <CopyField label="Relative path" value={node.relative_path} onCopy={onCopy} />
      {node.browse_error ? (
        <div className="rounded border border-red-300 bg-red-50 p-2 text-xs text-red-800">
          {node.browse_error}
        </div>
      ) : null}
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs font-semibold uppercase text-slate-500">{label}</div>
      <div className="mt-1 break-all rounded border border-line bg-slate-50 p-2 font-mono text-xs">
        {value}
      </div>
    </div>
  );
}

function CopyField({
  label,
  value,
  onCopy
}: {
  label: string;
  value: string;
  onCopy: (value: string) => void;
}) {
  return (
    <div>
      <div className="text-xs font-semibold uppercase text-slate-500">{label}</div>
      <div className="mt-1 flex gap-2">
        <code className="min-w-0 flex-1 break-all rounded border border-line bg-slate-50 p-2 text-xs">
          {value}
        </code>
        <button
          type="button"
          onClick={() => onCopy(value)}
          className="h-9 rounded border border-line px-3 text-xs"
        >
          Copy
        </button>
      </div>
    </div>
  );
}

function BrowserSettingsModal({
  endpoint,
  username,
  password,
  onEndpointChange,
  onUsernameChange,
  onPasswordChange,
  onConnect,
  onClose
}: {
  endpoint: string;
  username: string;
  password: string;
  onEndpointChange: (value: string) => void;
  onUsernameChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onConnect: () => void;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 px-4 py-6"
      onClick={onClose}
    >
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="browser-settings-title"
        className="w-full max-w-xl rounded-md border border-line bg-white shadow-xl"
        onSubmit={(event) => {
          event.preventDefault();
          void onConnect();
        }}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <h2 id="browser-settings-title" className="text-base font-semibold">
            OPC UA connection
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-line px-2 py-1 text-sm"
          >
            Close
          </button>
        </div>
        <div className="grid gap-3 p-4">
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
            Endpoint URL
            <input
              value={endpoint}
              onChange={(event) => onEndpointChange(event.target.value)}
              className="h-9 rounded border border-line bg-white px-2 font-mono text-sm text-ink"
              placeholder="opc.tcp://127.0.0.1:4840"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
            Username
            <input
              value={username}
              onChange={(event) => onUsernameChange(event.target.value)}
              className="h-9 rounded border border-line bg-white px-2 text-sm text-ink"
              autoComplete="username"
              placeholder="optional"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
            Password
            <input
              value={password}
              onChange={(event) => onPasswordChange(event.target.value)}
              className="h-9 rounded border border-line bg-white px-2 text-sm text-ink"
              type="password"
              autoComplete="current-password"
              placeholder="optional"
            />
          </label>
        </div>
        <div className="flex justify-end gap-2 border-t border-line bg-slate-50 px-4 py-3">
          <button
            type="button"
            onClick={onClose}
            className="h-9 rounded border border-line bg-white px-4 text-sm"
          >
            Cancel
          </button>
          <button type="submit" className="h-9 rounded bg-accent px-4 text-sm font-medium text-white">
            Connect
          </button>
        </div>
      </form>
    </div>
  );
}

function CopyMenu({
  menu,
  onCopy
}: {
  menu: { x: number; y: number; node: BrowserNode };
  onCopy: (value: string) => void;
}) {
  return (
    <div
      className="fixed z-50 min-w-44 rounded-md border border-line bg-white p-1 text-sm shadow-xl"
      style={{ left: menu.x, top: menu.y }}
      onClick={(event) => event.stopPropagation()}
    >
      <button
        type="button"
        onClick={() => onCopy(menu.node.node_id)}
        className="block w-full rounded px-3 py-2 text-left hover:bg-slate-100"
      >
        Copy node ID
      </button>
      <button
        type="button"
        onClick={() => onCopy(menu.node.path)}
        className="block w-full rounded px-3 py-2 text-left hover:bg-slate-100"
      >
        Copy full path
      </button>
      <button
        type="button"
        onClick={() => onCopy(menu.node.relative_path)}
        className="block w-full rounded px-3 py-2 text-left hover:bg-slate-100"
      >
        Copy relative path
      </button>
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

function formatBrowserValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

function findNode(node: BrowserNode, nodeId: string): BrowserNode | null {
  if (node.node_id === nodeId) {
    return node;
  }
  for (const child of node.children) {
    const found = findNode(child, nodeId);
    if (found) {
      return found;
    }
  }
  return null;
}

function replaceNode(current: BrowserNode, replacement: BrowserNode): BrowserNode {
  if (current.node_id === replacement.node_id) {
    return replacement;
  }
  return {
    ...current,
    children: current.children.map((child) => replaceNode(child, replacement))
  };
}

function collectExpandableNodeIds(node: BrowserNode, output: Set<string>) {
  if (node.has_children) {
    output.add(node.node_id);
  }
  for (const child of node.children) {
    collectExpandableNodeIds(child, output);
  }
}
