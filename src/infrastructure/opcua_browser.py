from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse, urlunparse

from asyncua import Client, ua

from src.infrastructure.asyncua_compat import patch_asyncua_python314_annotations


DEFAULT_BROWSER_MAX_DEPTH = 6
DEFAULT_BROWSER_MAX_NODES = 500


@dataclass(frozen=True)
class BrowserConnection:
    endpoint: str
    username: str | None = None
    password: str | None = None

    def __post_init__(self) -> None:
        endpoint = self.endpoint.strip()
        if not endpoint:
            raise ValueError("OPC UA endpoint must not be empty")
        object.__setattr__(self, "endpoint", endpoint)
        object.__setattr__(self, "username", _clean_optional(self.username))
        object.__setattr__(self, "password", _clean_optional(self.password))


@dataclass(frozen=True)
class BrowserNode:
    node_id: str
    browse_name: str
    display_name: str
    node_class: str
    path: str
    relative_path: str
    has_children: bool
    child_count: int | None
    value: Any | None = None
    value_error: str | None = None
    browse_error: str | None = None
    children: list["BrowserNode"] = field(default_factory=list)


@dataclass(frozen=True)
class BrowseResult:
    node: BrowserNode
    truncated: bool = False
    visited_nodes: int = 0


class OpcuaBrowser:
    async def browse(
        self,
        connection: BrowserConnection,
        *,
        node_id: str | None = None,
        path: str | None = None,
        relative_path: str | None = None,
    ) -> BrowseResult:
        async with _client(connection) as client:
            node = client.get_node(node_id) if node_id else client.get_objects_node()
            browser_node = await _read_node(
                node,
                path=path,
                relative_path=relative_path,
                include_children=True,
            )
            return BrowseResult(node=browser_node, visited_nodes=1 + len(browser_node.children))

    async def expand(
        self,
        connection: BrowserConnection,
        *,
        node_id: str | None = None,
        path: str | None = None,
        relative_path: str | None = None,
        max_depth: int = DEFAULT_BROWSER_MAX_DEPTH,
        max_nodes: int = DEFAULT_BROWSER_MAX_NODES,
    ) -> BrowseResult:
        if max_depth < 1:
            raise ValueError("max_depth must be at least 1")
        if max_nodes < 1:
            raise ValueError("max_nodes must be at least 1")

        async with _client(connection) as client:
            remaining = _BrowseBudget(max_nodes=max_nodes)
            node = client.get_node(node_id) if node_id else client.get_objects_node()
            browser_node = await _expand_node(
                node,
                path=path,
                relative_path=relative_path,
                depth=0,
                max_depth=max_depth,
                budget=remaining,
            )
            return BrowseResult(
                node=browser_node,
                truncated=remaining.truncated,
                visited_nodes=remaining.visited_nodes,
            )


def browser_default_endpoint(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if parsed.hostname not in {"0.0.0.0", "::"}:
        return endpoint

    netloc = "127.0.0.1"
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))


class _BrowseBudget:
    def __init__(self, max_nodes: int) -> None:
        self.max_nodes = max_nodes
        self.visited_nodes = 0
        self.truncated = False

    def take(self) -> bool:
        if self.visited_nodes >= self.max_nodes:
            self.truncated = True
            return False
        self.visited_nodes += 1
        return True


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _client(connection: BrowserConnection) -> Client:
    patch_asyncua_python314_annotations()
    client = Client(url=connection.endpoint, timeout=4)
    if connection.username is not None:
        client.set_user(connection.username)
    if connection.password is not None:
        client.set_password(connection.password)
    return client


async def _read_node(
    node: Any,
    *,
    path: str | None,
    relative_path: str | None,
    include_children: bool,
) -> BrowserNode:
    node_id = node.nodeid.to_string()
    browse_name = await _safe_browse_name(node)
    display_name = await _safe_display_name(node)
    node_path = path or display_name or browse_name or node_id
    node_relative_path = relative_path or display_name or browse_name or node_id
    node_class = await _safe_node_class(node)
    value, value_error = await _safe_value(node, node_class)

    children: list[BrowserNode] = []
    child_count: int | None = None
    browse_error: str | None = None
    try:
        child_nodes = await node.get_children(refs=ua.ObjectIds.HierarchicalReferences)
        child_count = len(child_nodes)
        if include_children:
            for child in child_nodes:
                child_display_name = await _safe_display_name(child)
                child_browse_name = await _safe_browse_name(child)
                child_label = child_display_name or child_browse_name or child.nodeid.to_string()
                children.append(
                    await _read_node(
                        child,
                        path=f"{node_path}/{child_label}",
                        relative_path=f"{node_relative_path}/{child_label}",
                        include_children=False,
                    )
                )
    except Exception as error:  # noqa: BLE001 - OPC UA servers can raise vendor-specific errors.
        browse_error = str(error)

    return BrowserNode(
        node_id=node_id,
        browse_name=browse_name,
        display_name=display_name,
        node_class=node_class,
        path=node_path,
        relative_path=node_relative_path,
        has_children=bool(child_count),
        child_count=child_count,
        value=_jsonable_value(value),
        value_error=value_error,
        browse_error=browse_error,
        children=children,
    )


async def _expand_node(
    node: Any,
    *,
    path: str | None,
    relative_path: str | None,
    depth: int,
    max_depth: int,
    budget: _BrowseBudget,
) -> BrowserNode:
    if not budget.take():
        display_name = await _safe_display_name(node)
        browse_name = await _safe_browse_name(node)
        return BrowserNode(
            node_id=node.nodeid.to_string(),
            browse_name=browse_name,
            display_name=display_name,
            node_class=await _safe_node_class(node),
            path=path or display_name or browse_name or node.nodeid.to_string(),
            relative_path=relative_path or display_name or browse_name or node.nodeid.to_string(),
            has_children=False,
            child_count=None,
            browse_error="browse limit reached",
        )

    current = await _read_node(
        node,
        path=path,
        relative_path=relative_path,
        include_children=False,
    )
    if depth >= max_depth:
        if current.has_children:
            budget.truncated = True
        return current

    try:
        child_nodes = await node.get_children(refs=ua.ObjectIds.HierarchicalReferences)
    except Exception:
        return current

    children: list[BrowserNode] = []
    for child in child_nodes:
        if budget.truncated:
            break
        child_display_name = await _safe_display_name(child)
        child_browse_name = await _safe_browse_name(child)
        child_label = child_display_name or child_browse_name or child.nodeid.to_string()
        children.append(
            await _expand_node(
                child,
                path=f"{current.path}/{child_label}",
                relative_path=f"{current.relative_path}/{child_label}",
                depth=depth + 1,
                max_depth=max_depth,
                budget=budget,
            )
        )

    return BrowserNode(
        node_id=current.node_id,
        browse_name=current.browse_name,
        display_name=current.display_name,
        node_class=current.node_class,
        path=current.path,
        relative_path=current.relative_path,
        has_children=current.has_children,
        child_count=current.child_count,
        value=current.value,
        value_error=current.value_error,
        browse_error=current.browse_error,
        children=children,
    )


async def _safe_display_name(node: Any) -> str:
    try:
        display_name = await node.read_display_name()
    except Exception:  # noqa: BLE001
        return ""
    return str(display_name.Text or "")


async def _safe_browse_name(node: Any) -> str:
    try:
        browse_name = await node.read_browse_name()
    except Exception:  # noqa: BLE001
        return ""
    return f"{browse_name.NamespaceIndex}:{browse_name.Name}"


async def _safe_node_class(node: Any) -> str:
    try:
        node_class = await node.read_node_class()
    except Exception as error:  # noqa: BLE001
        return f"Unknown ({error})"
    return getattr(node_class, "name", str(node_class))


async def _safe_value(node: Any, node_class: str) -> tuple[Any | None, str | None]:
    if node_class != "Variable":
        return None, None
    try:
        return await node.read_value(), None
    except Exception as error:  # noqa: BLE001
        return None, str(error)


def _jsonable_value(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list | tuple):
        return [_jsonable_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable_value(item) for key, item in value.items()}
    return str(value)
