---
name: prime-intellect
description: Manage Prime Intellect GPU compute — launch instances, check availability, monitor pods. Use when the user asks about GPU rental, spinning up machines, training runs, or Prime Intellect.
---

# Prime Intellect GPU Compute

Manage GPU instances on Prime Intellect via the CLI at `tools/prime/`.

## Setup

Requires `PRIMEINTELLECT_API_KEY` (or `PRIME_INTELLECT_API_KEY` or `PRIME_API_KEY`) in `.env`.
Generate at https://app.primeintellect.ai/dashboard/tokens — needs `Instances -> Read and write` + `Availability -> Read` permissions.

## CLI

All commands output JSON to stdout. Run from `tools/prime/`:

```bash
cd tools/prime && uv run python -m prime_intellect <command>
```

### Availability

```bash
# List all GPU types
uv run python -m prime_intellect gpu-types

# Pricing summary by GPU type
uv run python -m prime_intellect gpu-summary

# List available offers (compact: cloudId, price, provider, stock)
uv run python -m prime_intellect availability --gpu-type H100_80GB --gpu-count 1 --available

# All filters
uv run python -m prime_intellect availability \
  --gpu-type H100_80GB \
  --gpu-count 1 \
  --regions united_states,canada \
  --socket SXM \
  --available

# Full unabridged offer JSON (includes disk/vcpu/memory specs, all images)
uv run python -m prime_intellect availability --gpu-type H100_80GB --full
```

### Create a Pod

Copy `cloudId`, `gpuType`, `socket`, `provider`, `dataCenter` from an availability offer:

```bash
uv run python -m prime_intellect create \
  --name my-training-run \
  --cloud-id "1H100.80S.32V" \
  --gpu-type H100_80GB \
  --socket SXM5 \
  --gpu-count 1 \
  --image ubuntu_22_cuda_12 \
  --provider datacrunch \
  --data-center FIN-02 \
  --country FI \
  --disk-size 200

# With env vars and custom disk
uv run python -m prime_intellect create \
  --name rl-run \
  --cloud-id "gpu_1x_h100" \
  --gpu-type H100_80GB \
  --socket PCIe \
  --gpu-count 1 \
  --image ubuntu_22_cuda_12 \
  --provider massedcompute \
  --env HF_TOKEN=xxx \
  --env WANDB_KEY=yyy \
  --max-price 3.00
```

Optional flags: `--disk-size`, `--vcpus`, `--memory`, `--max-price`, `--template`, `--team-id`, `--disks` (comma-separated IDs), `--env KEY=val` (repeatable), `--share-with-team`.

### Manage Pods

```bash
# List running pods
uv run python -m prime_intellect list

# Full pod JSON
uv run python -m prime_intellect list --full

# Detailed status (SSH, install progress, ports, resources)
uv run python -m prime_intellect status <pod_id>

# Pod logs
uv run python -m prime_intellect logs <pod_id>

# Terminate a pod
uv run python -m prime_intellect terminate <pod_id>

# History of past (terminated) pods
uv run python -m prime_intellect history
```

## Workflow: Launch a GPU

1. **Find offers**: `availability --gpu-type H100_80GB --available` — pick cheapest or preferred region
2. **Create pod**: `create` with values from the offer (`cloudId`, `socket`, `provider`, `dataCenter`, pick an `image`)
3. **Wait for ready**: poll `status <pod_id>` — look for `sshConnection` to be populated and `installationStatus: FINISHED`
4. **Connect**: `ssh -i ~/.ssh/id_ed25519 <sshConnection>`
5. **Clean up**: `terminate <pod_id>` when done

## Key Fields in Availability Output

| Field | Description |
|-------|-------------|
| `cloudId` | Required for create — unique offer identifier |
| `gpuType` | e.g. `H100_80GB`, `A100_80GB`, `RTX4090_24GB` |
| `socket` | `PCIe`, `SXM`, `SXM5` |
| `provider` | `datacrunch`, `hyperstack`, `massedcompute`, `runpod`, etc. |
| `price` | USD per hour (on-demand) |
| `stock` | `Available`, `Low`, or `Unavailable` |
| `images` | Available OS images (usually `ubuntu_22_cuda_12` is the default) |
| `dataCenter` | Pass as `--data-center` if present |

## Rules

- Always check `--available` when looking for GPUs to launch — no point showing out-of-stock offers
- When creating pods for the user, confirm the price before provisioning
- Prefer cheapest available offer unless user specifies region/provider preference
- Never log or expose the API key
- Terminate pods when user says they're done — these cost money per hour
