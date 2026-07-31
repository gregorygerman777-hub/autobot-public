"""GPU and disk availability queries."""

from __future__ import annotations

from typing import Any

from prime_intellect.client import get

DEFAULT_PAGE_SIZE = 100


def _fetch_all(path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Paginate through all results."""
    page = 1
    results: list[dict[str, Any]] = []
    while True:
        p = {**params, "page": page, "page_size": DEFAULT_PAGE_SIZE}
        resp = get(path, params=p)
        items = resp.get("items", [])
        results.extend(items)
        if len(results) >= resp.get("totalCount", 0):
            break
        page += 1
    return results


def list_gpus(
    *,
    gpu_type: str | None = None,
    gpu_count: int | None = None,
    regions: list[str] | None = None,
    socket: str | None = None,
    available_only: bool = False,
) -> list[dict[str, Any]]:
    """Return GPU availability offers."""
    params: dict[str, Any] = {}
    if gpu_type:
        params["gpu_type"] = gpu_type
    if gpu_count:
        params["gpu_count"] = str(gpu_count)
    if regions:
        params["regions"] = regions
    if socket:
        params["socket"] = socket

    items = _fetch_all("/availability/gpus", params)
    if available_only:
        items = [i for i in items if i.get("stockStatus") in ("Available", "Low")]
    return items


def gpu_types() -> list[str]:
    """Return list of available GPU type names."""
    resp = get("/availability/gpu-summary")
    return sorted(resp.keys())


def gpu_summary() -> dict[str, Any]:
    """Return GPU pricing summary grouped by type."""
    return get("/availability/gpu-summary")
