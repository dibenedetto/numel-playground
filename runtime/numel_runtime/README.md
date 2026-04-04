# `numel-runtime`

Reference production runtime images for Numel executions.

Build from the repository root:

```bash
docker build -f runtime/numel_runtime/Dockerfile -t numel-runtime:latest .
docker build -f runtime/numel_runtime/Dockerfile.cuda -t numel-runtime:cuda .
```

Image roles:

- `numel-runtime:latest`
  CPU-oriented runtime image.
  PyTorch is pinned to `torch==2.10.0`, `torchvision==0.25.0`, and `torchaudio==2.10.0` from the official CPU wheel index.
- `numel-runtime:cuda`
  GPU-oriented runtime image for workflows whose runtime profile sets `gpu_enabled=true`.
  The base image targets CUDA `12.8.1`, and PyTorch is pinned to the official `cu128` wheel set: `torch==2.10.0`, `torchvision==0.25.0`, `torchaudio==2.10.0`.

The container expects:

- a read-only workflow snapshot mounted at `/workspace`
- a writable artifacts directory mounted at `/artifacts`
- the `NUMEL_*` environment contract defined in `app/platform_prod/runtime_contract.py`

The runtime entrypoint now executes the target workflow through Numel's in-process engine path and writes:

- `/artifacts/outputs.json`
- `/artifacts/status.json`
- `/artifacts/error.txt` on failure

Compose deployment note:

- the production compose stack uses deploy/runtime-builder.sh to rebuild 
umel-runtime:latest and 
umel-runtime:cuda only when runtime-relevant sources change or the target image is missing

Docker API behavior:

- when `runtime.image` is set, Numel uses it directly
- otherwise, Numel uses `runtime.default_image`
- if `gpu_enabled=true` and no explicit image override is present, Numel prefers `runtime.default_gpu_image`
- GPU-enabled runs also emit a Docker `DeviceRequests` block using `runtime.gpu_driver` and `runtime.gpu_device_count`

Important note:

- the CUDA image assumes a host NVIDIA driver compatible with CUDA 12.8+
- if you later move beyond the official `cu128` wheel set, pin the exact replacement wheel set intentionally instead of relaxing these versions back to open-ended ranges
