# Runtime Container Contract

Numel's production runtime launches a container image, currently scaffolded as `numel-runtime`, against a materialized space snapshot.

The contract is shared in code at [app/platform_prod/runtime_contract.py](/c:/devel/numel-playground/app/platform_prod/runtime_contract.py).

## Mounts

The Docker runtime adapter mounts:

- the selected space/ref snapshot read-only at `/workspace`
- the execution artifact directory read-write at `/artifacts`

By default, the production Docker spec also hardens the container with a read-only root filesystem, dropped Linux capabilities, `no-new-privileges`, `tmpfs` scratch mounts for `/tmp` and `/run`, and a PID limit. These defaults are configurable through the `runtime` section in `app/platform_backend.json`.

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

Resolved credential values and runtime-profile env vars are injected alongside these. In the production adapter, user-scope and matching space-scope credentials are merged for each execution, and the host-side diagnostic `job_spec.json` redacts those injected values.

## Files

The current runtime image contract writes:

- `outputs.json`
  Purpose: structured outputs for Numel to surface back through `/executions/*`
- `status.json`
  Purpose: execution metadata such as contract version, state, timestamps, input keys, and asset details
- `error.txt`
  Purpose: a human-readable failure reason when the container exits unsuccessfully

Numel stores a host-side diagnostic `job_spec.json` beside the execution artifact directory, but that file is not part of the container input contract. Injected credential/env values are redacted there.

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

This runtime image now executes the selected workflow through Numel's in-process `WorkflowManager + WorkflowEngine` path inside the container and writes contract-shaped artifacts back to `/artifacts`. The production adapter now also applies quota-aware concurrent-run checks, wall-clock timeout enforcement, merged user/space secret injection, host-side env redaction, container removal on terminal completion, snapshot cleanup, and artifact-retention pruning. The remaining work is mainly the final production image/dependency policy and the external secrets deployment choice, rather than the absence of a real runtime lifecycle.


