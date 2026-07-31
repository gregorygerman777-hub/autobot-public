"""Prime Intellect CLI. Run with: python -m prime_intellect <command> [args]"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def _json_out(data: Any) -> None:
    json.dump(data, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


# ── availability ────────────────────────────────────────────────────

def cmd_availability(args: argparse.Namespace) -> None:
    from prime_intellect.availability import list_gpus

    regions = args.regions.split(",") if args.regions else None
    items = list_gpus(
        gpu_type=args.gpu_type,
        gpu_count=args.gpu_count,
        regions=regions,
        socket=args.socket,
        available_only=args.available,
    )

    # Compact summary by default, full JSON with --full
    if args.full:
        _json_out(items)
        return

    rows = []
    for g in items:
        price = g.get("prices", {}).get("onDemand")
        rows.append({
            "cloudId": g["cloudId"],
            "gpuType": g["gpuType"],
            "socket": g.get("socket"),
            "gpuCount": g["gpuCount"],
            "gpuMemory": g.get("gpuMemory"),
            "provider": g.get("provider"),
            "dataCenter": g.get("dataCenter"),
            "country": g.get("country"),
            "stock": g.get("stockStatus"),
            "price": price,
            "images": g.get("images", []),
        })
    rows.sort(key=lambda r: (r["price"] or 999, r["gpuType"]))
    _json_out(rows)


def cmd_gpu_types(args: argparse.Namespace) -> None:
    from prime_intellect.availability import gpu_types

    _json_out(gpu_types())


def cmd_gpu_summary(args: argparse.Namespace) -> None:
    from prime_intellect.availability import gpu_summary

    _json_out(gpu_summary())


# ── pods ────────────────────────────────────────────────────────────

def cmd_list(args: argparse.Namespace) -> None:
    from prime_intellect.pods import list_pods

    result = list_pods(offset=args.offset, limit=args.limit)
    pods = result.get("data", [])

    if args.full:
        _json_out(pods)
        return

    rows = []
    for p in pods:
        rows.append({
            "id": p["id"],
            "name": p.get("name"),
            "gpu": f"{p['gpuName']} x{p['gpuCount']}",
            "status": p["status"],
            "provider": p.get("providerType"),
            "price": p.get("priceHr"),
            "ssh": p.get("sshConnection"),
            "ip": p.get("ip"),
            "created": p.get("createdAt"),
        })
    _json_out(rows)


def cmd_status(args: argparse.Namespace) -> None:
    from prime_intellect.pods import get_pod, get_status

    pod = get_pod(args.pod_id)
    statuses = get_status([args.pod_id])
    status = statuses[0] if statuses else {}

    result = {
        "id": pod["id"],
        "name": pod.get("name"),
        "status": pod["status"],
        "gpu": f"{pod['gpuName']} x{pod['gpuCount']}",
        "socket": pod.get("socket"),
        "provider": pod.get("providerType"),
        "image": pod.get("environmentType"),
        "price": pod.get("priceHr"),
        "ssh": status.get("sshConnection") or pod.get("sshConnection"),
        "ip": status.get("ip") or pod.get("ip"),
        "installationStatus": pod.get("installationStatus"),
        "installationProgress": status.get("installationProgress"),
        "resources": pod.get("resources"),
        "portMappings": status.get("primePortMapping"),
        "attachedResources": pod.get("attachedResources"),
        "created": pod.get("createdAt"),
        "teamId": pod.get("teamId"),
    }
    _json_out(result)


def cmd_create(args: argparse.Namespace) -> None:
    from prime_intellect.pods import create_pod

    env_vars = None
    if args.env:
        env_vars = []
        for e in args.env:
            k, v = e.split("=", 1)
            env_vars.append({"key": k, "value": v})

    disks = args.disks.split(",") if args.disks else None

    result = create_pod(
        name=args.name,
        cloud_id=args.cloud_id,
        gpu_type=args.gpu_type,
        socket=args.socket,
        gpu_count=args.gpu_count,
        image=args.image,
        provider=args.provider,
        data_center_id=args.data_center,
        country=args.country,
        security=args.security,
        disk_size=args.disk_size,
        vcpus=args.vcpus,
        memory=args.memory,
        max_price=args.max_price,
        custom_template_id=args.template,
        team_id=args.team_id,
        disks=disks,
        env_vars=env_vars,
        shared_with_team=args.share_with_team,
    )
    _json_out(result)


def cmd_terminate(args: argparse.Namespace) -> None:
    from prime_intellect.pods import terminate_pod

    terminate_pod(args.pod_id)
    _json_out({"status": "terminated", "podId": args.pod_id})


def cmd_history(args: argparse.Namespace) -> None:
    from prime_intellect.pods import pod_history

    _json_out(pod_history(offset=args.offset, limit=args.limit))


def cmd_logs(args: argparse.Namespace) -> None:
    from prime_intellect.pods import pod_logs

    _json_out(pod_logs(args.pod_id))


# ── main ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="prime_intellect",
        description="Prime Intellect GPU compute CLI",
    )
    sub = parser.add_subparsers(dest="command")

    # availability
    p_avail = sub.add_parser("availability", help="List GPU availability")
    p_avail.add_argument("--gpu-type", help="Filter by GPU type (e.g. H100_80GB)")
    p_avail.add_argument("--gpu-count", type=int, help="Filter by GPU count")
    p_avail.add_argument("--regions", help="Comma-separated regions")
    p_avail.add_argument("--socket", help="Filter by socket (PCIe, SXM)")
    p_avail.add_argument("--available", action="store_true", help="Only in-stock offers")
    p_avail.add_argument("--full", action="store_true", help="Full JSON (not compact)")
    p_avail.set_defaults(func=cmd_availability)

    # gpu-types
    p_gputypes = sub.add_parser("gpu-types", help="List available GPU type names")
    p_gputypes.set_defaults(func=cmd_gpu_types)

    # gpu-summary
    p_gpusum = sub.add_parser("gpu-summary", help="GPU pricing summary by type")
    p_gpusum.set_defaults(func=cmd_gpu_summary)

    # list
    p_list = sub.add_parser("list", help="List running pods")
    p_list.add_argument("--offset", type=int, default=0)
    p_list.add_argument("--limit", type=int, default=100)
    p_list.add_argument("--full", action="store_true", help="Full JSON per pod")
    p_list.set_defaults(func=cmd_list)

    # status
    p_status = sub.add_parser("status", help="Get pod details")
    p_status.add_argument("pod_id", help="Pod ID")
    p_status.set_defaults(func=cmd_status)

    # create
    p_create = sub.add_parser("create", help="Create (provision) a GPU pod")
    p_create.add_argument("--name", required=True, help="Pod name")
    p_create.add_argument("--cloud-id", required=True, help="Cloud ID from availability")
    p_create.add_argument("--gpu-type", required=True, help="GPU type (e.g. H100_80GB)")
    p_create.add_argument("--socket", required=True, help="Socket type (PCIe, SXM)")
    p_create.add_argument("--gpu-count", type=int, required=True, help="Number of GPUs")
    p_create.add_argument("--image", required=True, help="Image name")
    p_create.add_argument("--provider", required=True, help="Provider name")
    p_create.add_argument("--data-center", help="Data center ID")
    p_create.add_argument("--country", help="Country code")
    p_create.add_argument("--security", help="Security type")
    p_create.add_argument("--disk-size", type=int, help="Disk size in GB")
    p_create.add_argument("--vcpus", type=int, help="vCPU count")
    p_create.add_argument("--memory", type=int, help="Memory in GB")
    p_create.add_argument("--max-price", type=float, help="Max hourly price cap")
    p_create.add_argument("--template", help="Custom template ID")
    p_create.add_argument("--team-id", help="Team ID")
    p_create.add_argument("--disks", help="Comma-separated disk IDs to attach")
    p_create.add_argument("--env", action="append", help="Env var KEY=value (repeatable)")
    p_create.add_argument("--share-with-team", action="store_true")
    p_create.set_defaults(func=cmd_create)

    # terminate
    p_term = sub.add_parser("terminate", help="Terminate a pod")
    p_term.add_argument("pod_id", help="Pod ID")
    p_term.set_defaults(func=cmd_terminate)

    # history
    p_hist = sub.add_parser("history", help="List terminated pod history")
    p_hist.add_argument("--offset", type=int, default=0)
    p_hist.add_argument("--limit", type=int, default=100)
    p_hist.set_defaults(func=cmd_history)

    # logs
    p_logs = sub.add_parser("logs", help="Get pod logs")
    p_logs.add_argument("pod_id", help="Pod ID")
    p_logs.set_defaults(func=cmd_logs)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
