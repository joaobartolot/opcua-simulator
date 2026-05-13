import sys
from dataclasses import MISSING, Field, fields, is_dataclass
from types import ModuleType, UnionType
from typing import Any, Union, get_args, get_origin

from asyncua import ua
from asyncua.ua import ua_binary


def patch_asyncua_python314_annotations() -> None:
    """Fix asyncua generated dataclass annotations under Python 3.14."""
    if sys.version_info < (3, 14):
        return

    patched = False
    for module in _asyncua_ua_modules():
        patched = _patch_module_dataclasses(module) or patched

    if patched:
        ua_binary.create_type_serializer.cache_clear()
        ua_binary.create_dataclass_serializer.cache_clear()

    _install_serializer_patch()


def _asyncua_ua_modules() -> list[ModuleType]:
    return [
        module
        for name, module in sys.modules.items()
        if name == "asyncua.ua" or name.startswith("asyncua.ua.")
    ]


def _patch_module_dataclasses(module: ModuleType) -> bool:
    patched = False
    for item in vars(module).values():
        if isinstance(item, type) and is_dataclass(item):
            patched = _patch_dataclass_type(item) or patched
    return patched


def _patch_dataclass_type(dataclass_type: type[Any]) -> bool:
    patched = False
    annotations = getattr(dataclass_type, "__annotations__", {})
    for field in fields(dataclass_type):
        replacement = _patched_field_type(field.name, field.type, field.default_factory)
        if replacement is field.type:
            continue
        annotations[field.name] = replacement
        field.type = replacement
        patched = True
    return patched


def _patched_field_type(field_name: str, field_type: Any, default_factory: Any) -> Any:
    if isinstance(field_type, (property, Field)):
        return _replacement_type(field_name, default_factory) or field_type

    origin = get_origin(field_type)
    if origin not in (Union, UnionType):
        return field_type

    replacement = _replacement_type(field_name, default_factory)
    if replacement is None:
        return field_type

    patched_args = tuple(
        replacement if isinstance(arg, (property, Field)) else arg
        for arg in get_args(field_type)
    )
    if patched_args == get_args(field_type):
        return field_type
    return Union[patched_args]


def _install_serializer_patch() -> None:
    if getattr(ua_binary, "_opcua_simulator_python314_patch", False):
        return

    original_create_dataclass_serializer = ua_binary.create_dataclass_serializer

    def create_dataclass_serializer(dataclass_type: type[Any]) -> Any:
        if is_dataclass(dataclass_type):
            _patch_dataclass_type(dataclass_type)
        return original_create_dataclass_serializer(dataclass_type)

    create_dataclass_serializer.cache_clear = (  # type: ignore[attr-defined]
        original_create_dataclass_serializer.cache_clear
    )
    ua_binary.create_dataclass_serializer = create_dataclass_serializer
    ua_binary._opcua_simulator_python314_patch = True


def _replacement_type(field_name: str, default_factory: Any) -> type[Any] | None:
    if isinstance(default_factory, type):
        return default_factory

    candidate = getattr(ua, field_name.rstrip("_"), None)
    if isinstance(candidate, type):
        return candidate

    if default_factory is not MISSING:
        candidate = getattr(ua, type(default_factory).__name__, None)
        if isinstance(candidate, type):
            return candidate

    return None
