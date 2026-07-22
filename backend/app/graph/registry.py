"""Versioned graph registry used for checkpoint compatibility."""

from typing import Any


class GraphRegistry:
    def __init__(self) -> None:
        self._graphs: dict[str, Any] = {}

    def register(self, version: str, graph: Any) -> None:
        if version in self._graphs:
            raise ValueError(f"graph version already registered: {version}")
        self._graphs[version] = graph

    def get(self, version: str) -> Any:
        try:
            return self._graphs[version]
        except KeyError as exc:
            raise RuntimeError(f"unsupported graph version: {version}") from exc

