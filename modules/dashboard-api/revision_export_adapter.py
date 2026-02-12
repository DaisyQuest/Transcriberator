"""DT-019 revision/export adapter for dashboard API integration."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from pathlib import Path
import sys
from typing import Any


_ROOT = Path(__file__).resolve().parents[2]


def _load_module(module_name: str, relative_path: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, _ROOT / relative_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module for path {relative_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


api_mod = _load_module("dashboard_api_skeleton_dt019", "modules/dashboard-api/src/dashboard_api_skeleton.py")


@dataclass(frozen=True)
class ExportLinks:
    revision_id: str
    links: dict[str, str]


class DashboardRevisionExportAdapter:
    def __init__(self, service: api_mod.DashboardApiSkeleton | None = None) -> None:
        self._service = service or api_mod.DashboardApiSkeleton()

    @property
    def service(self) -> api_mod.DashboardApiSkeleton:
        return self._service

    def build_download_links(self, *, revision_id: str, export_manifest: dict[str, str], ttl_seconds: int) -> ExportLinks:
        if not revision_id.strip():
            raise api_mod.DashboardApiError(code="invalid_revision", message="Revision id is required.")
        if not export_manifest:
            raise api_mod.DashboardApiError(code="invalid_manifest", message="Export manifest cannot be empty.")

        links: dict[str, str] = {}
        for export_type in sorted(export_manifest):
            artifact_id = f"{revision_id}-{export_type}"
            links[export_type] = self._service.artifact_download_link(artifact_id=artifact_id, ttl_seconds=ttl_seconds)

        return ExportLinks(revision_id=revision_id, links=links)
