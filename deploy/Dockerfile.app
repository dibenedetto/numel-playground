FROM numel-runtime:latest AS base

WORKDIR /opt/numel

RUN python -m pip install --no-cache-dir "psycopg[binary]"

COPY app/ /opt/numel/app/
COPY web/ /opt/numel/web/
COPY contrib/ /opt/numel/contrib/
COPY examples/ /opt/numel/examples/
COPY docs/ /opt/numel/docs/
COPY models/ /opt/numel/models/
COPY runtime/ /opt/numel/runtime/
COPY deploy/ /opt/numel/deploy/
COPY README.md /opt/numel/README.md
COPY pyproject.toml /opt/numel/pyproject.toml

ENV PYTHONUNBUFFERED=1
ENV NUMEL_PORT=11360

EXPOSE 11360

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD curl -fsS http://localhost:${NUMEL_PORT}/health/ready || exit 1

CMD ["python", "app/app.py", "--port", "11360"]
