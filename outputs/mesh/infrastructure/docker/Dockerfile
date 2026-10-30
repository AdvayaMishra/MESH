FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704 AS builder
WORKDIR /build
COPY requirements-build.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements-build.lock
COPY pyproject.toml ./
COPY backend ./backend
RUN pip wheel --no-cache-dir --no-build-isolation --no-deps --no-index --wheel-dir /opt/mesh/dist .

FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/mesh
COPY requirements.lock requirements-hashed.lock requirements-build.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements-hashed.lock
COPY pyproject.toml ./
COPY backend ./backend
COPY scripts ./scripts
COPY alembic.ini ./
COPY supabase/supabase-ca.crt ./supabase/supabase-ca.crt
COPY --from=builder /opt/mesh/dist /opt/mesh/dist
RUN pip install --no-cache-dir --no-deps --no-index /opt/mesh/dist/mesh_backend-0.1.0-py3-none-any.whl && rm -r /opt/mesh/dist && useradd --uid 10001 --create-home mesh
USER 10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
