# syslog-fwd

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

A lightweight, pure Python syslog forwarder with simple YAML configuration.

## Features

- **Simple YAML configuration** - No complex rsyslog/syslog-ng syntax to learn
- **Multiple inputs** - Listen on UDP and TCP simultaneously
- **Flexible filtering** - Route messages by facility, severity, hostname, or content
- **Multiple destinations** - Forward to different servers based on rules
- **RFC compliant** - Supports RFC 3164 (BSD) and RFC 5424 (modern) formats
- **Prometheus metrics** - Built-in `/metrics` endpoint
- **Lightweight** - Single Python package, no external dependencies
- **Docker ready** - Official image available

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
```

## Metrics

Prometheus metrics available at `/metrics`:

- `syslog_messages_received_total{protocol,facility,severity}`
- `syslog_messages_forwarded_total{destination}`
- `syslog_messages_dropped_total{reason}`
- `syslog_destination_up{destination}`

Health check available at `/health`.

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

### Split by severity

```yaml
filters:
  - name: critical
    match:
      severity: [crit, alert, emerg]
    destinations: [pagerduty, archive]
  - name: errors
    match:
      severity: [err, warning]
    destinations: [errors-queue]
  - name: info
    destinations: [general]
```

## Development

```bash
# Clone repository
git clone https://github.com/brun_s/syslog-forwarder.git
cd syslog-forwarder

# Install dependencies
uv sync --dev

# Run tests
uv run pytest

# Run linter
uv run ruff check src/

# Install pre-commit hooks
uv run pre-commit install
```

## License

Apache License 2.0