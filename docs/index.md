# Syslog Forwarder

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A lightweight, pure Python syslog forwarder with simple YAML configuration.

## Features

- **Simple YAML configuration** - No complex rsyslog/syslog-ng syntax to learn
- **Multiple inputs** - Listen on UDP and TCP simultaneously
- **Flexible filtering** - Route messages by facility, severity, hostname, or content
- **Message transformation** - Rewrite, mask, or remove fields before forwarding
- **Multiple destinations** - Forward to different servers based on rules
- **RFC compliant** - Supports RFC 3164 (BSD) and RFC 5424 (modern) formats
- **Prometheus metrics** - Built-in `/metrics` endpoint
- **Lightweight** - Single Python package, minimal dependencies
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

## Example Configuration

```yaml
version: "1"

inputs:
  - name: udp-514
    protocol: udp
    address: "0.0.0.0:514"

filters:
  - name: security-logs
    match:
      facility: [auth, authpriv]
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
  metrics:
    enabled: true
    address: "0.0.0.0:9090"
```

## Documentation

- [User Guide](user-guide.md) - Complete usage documentation
- [Architecture](architecture.md) - Component models and diagrams
- [PRD](PRD.md) - Product requirements document

## License

MIT License - see [LICENSE](https://github.com/brunseba/syslog-forwarder/blob/main/LICENSE) for details.
