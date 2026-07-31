"""Pod (instance) management."""

from __future__ import annotations

from typing import Any

from prime_intellect.client import delete, get, post


def list_pods(*, offset: int = 0, limit: int = 100) -> dict[str, Any]:
    """List running pods. Returns {total_count, offset, limit, data: [...]}."""
    return get("/pods", params={"offset": offset, "limit": limit})


def get_pod(pod_id: str) -> dict[str, Any]:
    """Get full details of a single pod."""
    return get(f"/pods/{pod_id}")


def get_status(pod_ids: list[str]) -> list[dict[str, Any]]:
    """Get status for one or more pods."""
    resp = get("/pods/status", params={"pod_ids": pod_ids})
    return resp.get("data", [])


def create_pod(
    *,
    name: str,
    cloud_id: str,
    gpu_type: str,
    socket: str,
    gpu_count: int,
    image: str,
    provider: str,
    data_center_id: str | None = None,
    country: str | None = None,
    security: str | None = None,
    disk_size: int | None = None,
    vcpus: int | None = None,
    memory: int | None = None,
    max_price: float | None = None,
    custom_template_id: str | None = None,
    team_id: str | None = None,
    disks: list[str] | None = None,
    env_vars: list[dict[str, str]] | None = None,
    shared_with_team: bool = False,
) -> dict[str, Any]:
    """Create (provision) a new GPU pod."""
    pod: dict[str, Any] = {
        "name": name,
        "cloudId": cloud_id,
        "gpuType": gpu_type,
        "socket": socket,
        "gpuCount": gpu_count,
        "image": image,
    }
    if data_center_id:
        pod["dataCenterId"] = data_center_id
    if country:
        pod["country"] = country
    if security:
        pod["security"] = security
    if disk_size is not None:
        pod["diskSize"] = disk_size
    if vcpus is not None:
        pod["vcpus"] = vcpus
    if memory is not None:
        pod["memory"] = memory
    if max_price is not None:
        pod["maxPrice"] = max_price
    if custom_template_id:
        pod["customTemplateId"] = custom_template_id
        pod["image"] = "custom_template"
    if env_vars:
        pod["envVars"] = env_vars

    body: dict[str, Any] = {
        "pod": pod,
        "provider": {"type": provider},
    }
    if team_id:
        body["team"] = {"teamId": team_id}
    if disks:
        body["disks"] = disks
    if shared_with_team:
        body["sharedWithTeam"] = True

    return post("/pods", json=body)


def terminate_pod(pod_id: str) -> None:
    """Terminate (delete) a pod."""
    delete(f"/pods/{pod_id}")


def pod_history(*, offset: int = 0, limit: int = 100) -> dict[str, Any]:
    """List terminated pod history."""
    return get("/pods/history", params={"offset": offset, "limit": limit})


def pod_logs(pod_id: str) -> dict[str, Any]:
    """Get logs for a pod."""
    return get(f"/pods/{pod_id}/logs")
