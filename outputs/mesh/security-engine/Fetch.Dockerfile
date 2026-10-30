FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704
RUN apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=30 update && apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=30 install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
COPY security-engine/fetch.py security-engine/askpass.py /opt/mesh/
RUN chmod 0555 /opt/mesh/askpass.py
ENTRYPOINT ["python", "/opt/mesh/fetch.py"]
