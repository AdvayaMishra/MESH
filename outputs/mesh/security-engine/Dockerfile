FROM zricethezav/gitleaks:v8.24.3@sha256:e1b35e12a8c6fa8901f060459cfb6b2fc4c484d3afbe3b029733a3bbfab07055 AS gitleaks
FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704 AS semgrep-core
COPY security-engine/semgrep-artifact.lock /opt/mesh/semgrep-artifact.lock
RUN pip download --no-cache-dir --no-deps --require-hashes --dest /wheels -r /opt/mesh/semgrep-artifact.lock
COPY security-engine/extract_semgrep_core.py /opt/mesh/extract_semgrep_core.py
RUN python /opt/mesh/extract_semgrep_core.py /wheels /opt/semgrep-core
FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704
COPY --from=semgrep-core /opt/semgrep-core /opt/semgrep-core
COPY security-engine/requirements.lock /opt/mesh/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /opt/mesh/requirements.lock && useradd --uid 10001 --create-home scanner
COPY --from=gitleaks /usr/bin/gitleaks /usr/local/bin/gitleaks
COPY security-engine/entrypoint.py security-engine/dependencies.py security-engine/semgrep_core.py security-engine/rules.yml security-engine/bandit.ini security-engine/gitleaks.toml security-engine/gitleaks.ignore /opt/mesh/
ENV SEMGREP_SEND_METRICS=off SEMGREP_ENABLE_VERSION_CHECK=0 HOME=/tmp
ENV OTEL_SDK_DISABLED=true OTEL_PROPAGATORS=none OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none
USER 10001
ENTRYPOINT ["python", "/opt/mesh/entrypoint.py"]
