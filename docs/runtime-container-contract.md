# Runtime Container Contract

Numel's production runtime launches a container image, currently scaffolded as `numel-runtime`, against a materialized space snapshot.

The contract is shared in code at [app/platform_prod/runtime_contract.py](/c:/devel/numel-playground/app/platform_prod/runtime_contract.py).

## Mounts

The Docker runtime adapter mounts:

- the selected space/ref snapshot read-only at `/workspace`
- the execution artifact directory read-write at `/artifacts`

## Environment Variables

The runtime always receives these `NUMEL_*` variables:

| Variable | Meaning |
|---|---|
| `NUMEL_CONTRACT_VERSION` | Runtime contract version string |
| `NUMEL_EXECUTION_ID` | Numel execution id |
| `NUMEL_USER_ID` | Owning user id |
| `NUMEL_SPACE_ID` | Space id |
| `NUMEL_ASSET_PATH` | Relative asset path inside the mounted workspace |
| `NUMEL_ASSET_KIND` | Asset kind, for example `workflow` |
| `NUMEL_REF` | Executed ref/branch/tag |
| `NUMEL_INPUTS_JSON` | JSON object of execution inputs |
| `NUMEL_RUNTIME_PROFILE_ID` | Optional runtime profile id |
| `NUMEL_RUNTIME_PROFILE_NAME` | Optional runtime profile name |
| `NUMEL_WORKSPACE_DIR` | Mounted workspace root, usually `/workspace` |
| `NUMEL_ARTIFACTS_DIR` | Mounted artifact root, usually `/artifacts` |
| `NUMEL_OUTPUTS_PATH` | Expected outputs file path |
| `NUMEL_ERROR_PATH` | Expected error file path |
| `NUMEL_STATUS_PATH` | Expected status file path |

Resolved credential values and runtime-profile env vars are injected alongside these.

## Files

The current runtime image contract writes:

- `outputs.json`
  Purpose: structured outputs for Numel to surface back through `/executions/*`
- `status.json`
  Purpose: execution metadata such as contract version, state, timestamps, input keys, and asset details
- `error.txt`
  Purpose: a human-readable failure reason when the container exits unsuccessfully

Numel stores a host-side diagnostic `job_spec.json` beside the execution artifact directory, but that file is not part of the container input contract.

## Default Command

If a runtime profile does not override `metadata.container_command` and `runtime.default_command` is blank, Numel uses:

```bash
python -m runtime.numel_runtime.entrypoint
```

That entrypoint is scaffolded in [runtime/numel_runtime/entrypoint.py](/c:/devel/numel-playground/runtime/numel_runtime/entrypoint.py), and the corresponding image Dockerfile lives at [runtime/numel_runtime/Dockerfile](/c:/devel/numel-playground/runtime/numel_runtime/Dockerfile).

For GPU-capable runtimes, Numel also ships [runtime/numel_runtime/Dockerfile.cuda](/c:/devel/numel-playground/runtime/numel_runtime/Dockerfile.cuda). When a runtime profile sets `gpu_enabled=true`, the Docker adapter prefers `runtime.default_gpu_image` and emits a Docker `DeviceRequests` block for GPU access unless the runtime profile explicitly overrides `image`.

The current pinned runtime targets are:

- CPU image: `torch==2.10.0`, `torchvision==0.25.0`, `torchaudio==2.10.0` from the official CPU wheel index
- CUDA image: NVIDIA CUDA `12.8.1` runtime base plus the official PyTorch `cu128` wheel set `torch==2.10.0`, `torchvision==0.25.0`, `torchaudio==2.10.0`

## Current Scope

This runtime image now executes the selected workflow through Numel's in-process `WorkflowManager + WorkflowEngine` path inside the container and writes contract-shaped artifacts back to `/artifacts`. It is still not the final production runtime architecture, because secrets hardening, quota enforcement, and the fully isolated dependency/image policy are still evolving.
