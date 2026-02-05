# Stage 1: Build
FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy project files
COPY pyproject.toml .
COPY src/ src/

# Build wheel
RUN uv build --wheel

# Stage 2: Runtime
FROM python:3.12-slim

# Labels (OCI)
LABEL org.opencontainers.image.title="syslog-fwd"
LABEL org.opencontainers.image.description="Lightweight syslog forwarder with simple YAML configuration"
LABEL org.opencontainers.image.version="0.1.0"
LABEL org.opencontainers.image.source="https://github.com/brun_s/syslog-forwarder"
LABEL org.opencontainers.image.licenses="Apache-2.0"

# Create non-root user
RUN groupadd -r syslog && useradd -r -g syslog syslog

WORKDIR /app

# Copy wheel from builder and install
COPY --from=builder /app/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Create config directory
RUN mkdir -p /etc/syslog-fwd && chown syslog:syslog /etc/syslog-fwd

# Switch to non-root user
USER syslog

# Default config location
ENV SYSLOG_FWD_CONFIG=/etc/syslog-fwd/config.yaml

# Expose ports
# 514 - syslog (UDP/TCP)
# 9090 - Prometheus metrics
EXPOSE 514/udp
EXPOSE 514/tcp
EXPOSE 9090/tcp

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9090/health || exit 1

# Run forwarder
ENTRYPOINT ["syslog-fwd"]
CMD ["run", "--config", "/etc/syslog-fwd/config.yaml"]
