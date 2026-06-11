"""Internal: prompt-template rendering over a node's input and the store.

A template key resolves against the input value first (dict key or model field), then the
store by tag, with `{input}` standing for the whole incoming value. Shared by the atoms and
the blackboard rules; not part of the public surface.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from fedotmas.engine.contract import View


class _Scope:
    """Template namespace for str.format_map, which needs only __getitem__: input fields
    first, then store tags, then `input` for the whole incoming value. Raises KeyError for
    anything else, so a typo in a template names itself."""

    def __init__(self, value: Any, view: View) -> None:
        self._value = value
        self._view = view

    def __getitem__(self, key: str) -> Any:
        if isinstance(self._value, dict) and key in self._value:
            return self._value[key]
        if isinstance(self._value, BaseModel) and key in type(self._value).model_fields:
            return getattr(self._value, key)
        fact = self._view.get(key)
        if fact is not None:
            return fact.value
        if key == "input":
            return self._value
        raise KeyError(key)


def render(template: str, value: Any, view: View, node: str) -> str:
    try:
        return template.format_map(_Scope(value, view))
    except KeyError as e:
        raise RuntimeError(
            f"node {node!r}: template references {e.args[0]!r}, which is neither an "
            "input field nor a store tag"
        ) from None
