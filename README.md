# syslog-fwd

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub release](https://img.shields.io/github/v/release/brunseba/syslog-forwarder)](https://github.com/brunseba/syslog-forwarder/releases)
[![Documentation](https://img.shields.io/badge/docs-mkdocs-blue.svg)](https://brunseba.github.io/syslog-forwarder/)

A lightweight, pure Python syslog forwarder with simple YAML configuration.

## Features

- **Simple YAML configuration** - No complex rsyslog/syslog-ng syntax to learn
- **Multiple inputs** - Listen on UDP and TCP simultaneously
- **Flexible filtering** - Route messages by facility, severity, hostname, or content
- **Message transformation** - Rewrite, mask, or remove fields before forwarding
- **Multiple destinations** - Forward to different servers based on rules
- **RFC compliant** - Supports RFC 3164 (BSD) and RFC 5424 (modern) formats
- **Prometheus metrics** - Built-in `/metrics` and `/health` endpoints
- **Config export** - Convert to syslog-ng format for comparison/migration
- **Lightweight** - Single Python package, minimal dependencies
- **Docker ready** - Multi-stage build with monitoring stack

## Quick Start

### Install

```bash
# Using pipx (recommended)
pipx install syslog-fwd

# Using pip
pip install syslog-fwd

# Using uv
uv tool install syslog-fwd
```

### Configure

```bash
# Generate example configuration
syslog-fwd init -o config.yaml

# Edit to match your environment
vim config.yaml

# Validate configuration
syslog-fwd validate -c config.yaml
```

### Run

```bash
# Run forwarder
syslog-fwd run -c config.yaml

# Test with simulator
syslog-fwd simulate -d localhost:5514 -n 10 -p udp
```

## Configuration

```yaml
version: "1"

inputs:
  - name: udp-514
    protocol: udp
    address: "0.0.0.0:514"

  - name: tcp-514
    protocol: tcp
    address: "0.0.0.0:514"

filters:
  - name: security-logs
    match:
      facility: [auth, authpriv]
      severity: [warning, err, crit, alert, emerg]
    destinations: [siem]

  - name: drop-debug
    match:
      severity: [debug]
    action: drop

  - name: default
    destinations: [central]

destinations:
  - name: siem
    protocol: tcp
    address: "siem.example.com:514"
    format: rfc5424

  - name: central
    protocol: udp
    address: "logs.example.com:514"
    format: rfc3164

service:
  log_level: info
  metrics:
    enabled: true
    address: "0.0.0.0:9090"
```

## Docker

```bash
# Run with Docker
docker run -d \
  -p 514:514/udp \
  -p 514:514/tcp \
  -p 9090:9090 \
  -v $(pwd)/config.yaml:/etc/syslog-fwd/config.yaml \
  syslog-fwd:latest
```

## CLI Commands

```bash
syslog-fwd --help              # Show help
syslog-fwd --version           # Show version
syslog-fwd init                # Generate example config
syslog-fwd validate -c FILE    # Validate configuration
syslog-fwd run -c FILE         # Run forwarder
syslog-fwd simulate -d HOST    # Send test messages
syslog-fwd export -c FILE      # Export to syslog-ng format
```

## Metrics

Prometheus metrics available at `/metrics`:

- `syslog_messages_received_total{protocol,facility,severity}`
- `syslog_messages_forwarded_total{destination}`
- `syslog_messages_dropped_total{reason}`
- `syslog_destination_up{destination}`

Health check available at `/health`.

## Docker Compose with Monitoring

```bash
# Start with Prometheus + Grafana
make monitoring

# Access Grafana dashboard
open http://localhost:3000  # admin/admin

# Run performance test
make perf
```

See `docker-compose.yml` for full sandbox environment.

## Filter Examples

### Forward auth logs to SIEM

```yaml
filters:
  - name: auth-to-siem
    match:
      facility: [auth, authpriv]
    destinations: [siem]
```

### Drop debug, forward rest

```yaml
filters:
  - name: drop-debug
    match:
      severity: [debug]
    action: drop
  - name: forward-all
    destinations: [central]
```

## Transform Examples

### Anonymize IP addresses

```yaml
transforms:
  - name: anonymize-ip
    mask_patterns:
      - pattern: "\\b\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\b"
        replacement: "x.x.x.x"

filters:
  - name: forward-anonymized
    transforms: [anonymize-ip]
    destinations: [external-siem]
```

### Mask sensitive data

```yaml
transforms:
  - name: mask-secrets
    mask_patterns:
      - pattern: "(password|token|api_key)=[^\\s]+"
        replacement: "\\1=***REDACTED***"
      - pattern: "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{2,}"
        replacement: "***@***.***"

filters:
  - name: secure-forward
    transforms: [mask-secrets]
    destinations: [siem]
```

### Remove fields and rewrite hostname

```yaml
transforms:
  - name: cleanup
    remove_fields: [proc_id, structured_data]
    set_fields:
      hostname: "forwarded-logs"

filters:
  - name: forward-clean
    transforms: [cleanup]
    destinations: [central]
```

## Documentation

- [User Guide](https://brunseba.github.io/syslog-forwarder/user-guide/) - Complete usage documentation
- [Architecture](https://brunseba.github.io/syslog-forwarder/architecture/) - Component models and diagrams
- [Changelog](CHANGELOG.md) - Release history

## Development

```bash
# Clone repository
git clone https://github.com/brunseba/syslog-forwarder.git
cd syslog-forwarder

# Install dependencies
uv sync --dev

# Run tests
uv run pytest

# Run linter
uv run ruff check src/

# Install pre-commit hooks
uv run pre-commit install

# Build documentation
uv run mkdocs serve
```

## License

MIT License - see [LICENSE](LICENSE) for details.
