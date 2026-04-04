#
# Build from the repository root so the Dockerfile can copy shared sources:
#   docker build -f runtime/numel_runtime/Dockerfile -t numel-runtime:latest .

FROM python:3.12-slim

ARG TORCH_VERSION=2.10.0
ARG TORCHVISION_VERSION=0.25.0
ARG TORCHAUDIO_VERSION=2.10.0

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/numel

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/opt/numel/app:/opt/numel
ENV NUMEL_WORKSPACE_DIR=/workspace
ENV NUMEL_ARTIFACTS_DIR=/artifacts

COPY pyproject.toml README.md /opt/numel/
COPY app/ /opt/numel/app/
COPY runtime/ /opt/numel/runtime/
COPY contrib/ /opt/numel/contrib/

RUN python -c "import pathlib, tomllib; data = tomllib.loads(pathlib.Path('/opt/numel/pyproject.toml').read_text(encoding='utf-8')); deps = [d for d in data['project']['dependencies'] if not d.startswith('torch==') and not d.startswith('torchvision==') and not d.startswith('torchaudio==')]; pathlib.Path('/tmp/numel-deps.txt').write_text('\n'.join(deps) + '\n', encoding='utf-8')"

RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    torch==${TORCH_VERSION} \
    torchvision==${TORCHVISION_VERSION} \
    torchaudio==${TORCHAUDIO_VERSION}

RUN pip install --no-cache-dir -r /tmp/numel-deps.txt

RUN mkdir -p /workspace /artifacts

CMD ["python", "-m", "runtime.numel_runtime.entrypoint"]
