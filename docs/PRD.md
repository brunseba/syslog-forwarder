# Product Requirements Document (PRD)
# Syslog Forwarder

**Version**: 1.0.0  
**Date**: February 5, 2025  
**Status**: Draft  

---

## Executive Summary

A **lightweight, pure Python syslog forwarder** that receives syslog messages, filters them, and forwards to destinations. No wrapped servers, no complex dependencies - just a single service with simple YAML configuration.

**What it is**: A standalone syslog forwarding service  
**What it is NOT**: A syslog server manager, log aggregator, or rsyslog/syslog-ng wrapper

---

## 1. Problem Statement

Need a simple tool to:
- Receive syslog from multiple sources
- Filter based on facility, severity, or content
- Forward to one or more destinations
- Easy to configure without learning rsyslog/syslog-ng syntax

---

## 2. Core Features

### 2.1 Syslog Input
- Listen on UDP (RFC 5426)
- Listen on TCP (RFC 6587)
- Listen on TLS (RFC 5425) - Phase 2
- Auto-detect RFC 3164 (BSD) and RFC 5424 (modern) formats
- Configurable listen address and port

### 2.2 Filtering
- Filter by facility (kern, user, mail, daemon, auth, etc.)
- Filter by severity (emerg, alert, crit, err, warning, notice, info, debug)
- Filter by hostname pattern (regex) - Phase 2
- Filter by message content (regex) - Phase 2
- Drop action (discard matching messages)
- First-match-wins rule evaluation

### 2.3 Forwarding (Output)
- Forward to multiple destinations
- Protocols: UDP, TCP, TLS (Phase 2)
- Per-destination format selection (RFC 3164 or RFC 5424)
- Retry with exponential backoff
- Message buffer for unreachable destinations - Phase 2

### 2.4 Configuration
- Single YAML file
- Environment variable substitution (`${VAR}`)
- Hot-reload on SIGHUP
- Pydantic validation with clear error messages

---

## 3. Interfaces

### 3.1 CLI (`syslog-fwd`)

```bash
syslog-fwd run [--config config.yaml]      # Run forwarder (foreground)
syslog-fwd validate [--config config.yaml] # Validate config
syslog-fwd simulate --dest host:port       # Send test messages
syslog-fwd version                         # Show version
```

### 3.2 Web UI (Phase 2 - Optional)
- Simple read-only status page
- Counters: received, forwarded, dropped
- Destination health status
- Dark mode

### 3.3 Metrics
- Prometheus `/metrics` endpoint
- `syslog_messages_received_total{protocol,facility,severity}`
- `syslog_messages_forwarded_total{destination}`
- `syslog_messages_dropped_total{reason}`
- `syslog_destination_up{destination}`

---

## 4. Configuration Schema

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

---

## 5. Technology Stack

- **Language**: Python 3.10+
- **Package Manager**: uv
- **CLI**: Click
- **Config Validation**: Pydantic
- **Async I/O**: asyncio
- **Metrics**: prometheus-client
- **Logging**: structlog (JSON)
- **Distribution**: pipx, Docker

---

## 6. Non-Functional Requirements

### Performance
- Handle 10,000+ messages/second
- < 5ms processing latency
- Memory < 100MB under normal load

### Reliability
- Graceful shutdown (complete in-flight messages)
- Auto-reconnect to TCP destinations
- No message loss during config reload

### Deployment
- Single Python package (no external syslog server needed)
- Docker image < 100MB (slim base)
- Run as non-root user
- Health check endpoint `/health`

### Security
- TLS 1.2+ (Phase 2)
- No secrets in plaintext (env vars)
- SBOM included

---

## 7. Deliverables

### Phase 1 (MVP)
- [ ] Project structure (uv, src layout)
- [ ] YAML config with Pydantic validation
- [ ] UDP input listener
- [ ] TCP input listener
- [ ] RFC 3164 & 5424 message parsing
- [ ] Facility/severity filters
- [ ] UDP/TCP forwarding
- [ ] CLI: run, validate, version
- [ ] Prometheus metrics
- [ ] Docker image
- [ ] README with examples
- [ ] Unit tests

### Phase 2
- [ ] TLS input/output
- [ ] Regex filters (hostname, message)
- [ ] Simulator command
- [ ] Hot-reload (SIGHUP)
- [ ] Message buffer/queue
- [ ] Simple Web UI

---

## 8. Example Use Cases

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

---

## 9. Out of Scope

- Managing external syslog servers
- Agent-based architecture
- Log storage/persistence
- Log parsing/enrichment
- Multi-user/RBAC
- Visual config builder

---

## 10. Success Criteria

- 5-minute setup: download → configure → forward
- Config readable without documentation
- `docker run` just works
- RFC 3164 and 5424 compliance

---

## Appendix: RFC References

- [RFC 3164](https://datatracker.ietf.org/doc/html/rfc3164) - BSD Syslog Protocol
- [RFC 5424](https://datatracker.ietf.org/doc/html/rfc5424) - Syslog Protocol
- [RFC 5426](https://datatracker.ietf.org/doc/html/rfc5426) - Syslog over UDP
- [RFC 6587](https://datatracker.ietf.org/doc/html/rfc6587) - Syslog over TCP
