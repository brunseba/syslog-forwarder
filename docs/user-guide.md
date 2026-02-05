# Syslog Forwarder - User Guide

## Table of Contents
1. [Installation](#installation)
2. [Quick Start](#quick-start)
3. [Configuration](#configuration)
4. [CLI Commands](#cli-commands)
5. [Inputs](#inputs)
6. [Filters](#filters)
7. [Transformations](#transformations)
8. [Destinations](#destinations)
9. [Monitoring](#monitoring)
10. [Docker Deployment](#docker-deployment)
11. [Troubleshooting](#troubleshooting)

---

## Installation

### Using pipx (recommended)
```bash
pipx install syslog-fwd
```

### Using pip
```bash
pip install syslog-fwd
```

### Using uv
```bash
uv tool install syslog-fwd
```

### From source
```bash
git clone https://github.com/brun_s/syslog-forwarder.git
cd syslog-forwarder
uv sync
uv run syslog-fwd --help
```

---

## Quick Start

### 1. Generate configuration
```bash
syslog-fwd init -o config.yaml
```

### 2. Edit configuration
Customize `config.yaml` for your environment:
- Set input ports
- Define filter rules
- Configure destinations

### 3. Validate configuration
```bash
syslog-fwd validate -c config.yaml
```

### 4. Run the forwarder
```bash
syslog-fwd run -c config.yaml
```

### 5. Test with simulator
```bash
syslog-fwd simulate -d localhost:5514 -n 10 -p udp
```

---

## Configuration

Configuration uses YAML format with four main sections:

```yaml
version: "1"

inputs:       # Where to receive messages
filters:      # How to route messages
transforms:   # How to modify messages
destinations: # Where to send messages
service:      # Service settings
```

### Environment Variables
Use `${VAR}` or `${VAR:-default}` syntax:

```yaml
destinations:
  - name: siem
    address: "${SIEM_HOST:-siem.example.com}:${SIEM_PORT:-514}"
```

### Configuration Validation
Always validate before running:
```bash
syslog-fwd validate -c config.yaml
```

Output shows:
- Number of inputs, filters, transforms, destinations
- Input endpoints and protocols
- Filter routing summary
- Destination addresses and formats

---

## CLI Commands

### `syslog-fwd run`
Start the forwarder service.

```bash
syslog-fwd run -c config.yaml
```

Options:
- `-c, --config PATH` - Configuration file (default: `config.yaml`)

### `syslog-fwd validate`
Validate configuration without running.

```bash
syslog-fwd validate -c config.yaml
```

### `syslog-fwd init`
Generate example configuration.

```bash
syslog-fwd init -o config.yaml
```

### `syslog-fwd simulate`
Send test syslog messages.

```bash
syslog-fwd simulate -d localhost:5514 -n 100 -r 10 -p udp -f local0 -s info
```

Options:
- `-d, --dest HOST:PORT` - Destination address (required)
- `-p, --protocol [udp|tcp]` - Protocol (default: udp)
- `-n, --count N` - Number of messages (default: 10)
- `-r, --rate N` - Messages per second (default: 1.0)
- `-f, --facility NAME` - Syslog facility (default: local0)
- `-s, --severity NAME` - Syslog severity (default: info)

### `syslog-fwd export`
Export configuration to other formats.

```bash
# Export to syslog-ng format
syslog-fwd export -c config.yaml -f syslog-ng -o syslog-ng.conf
```

Options:
- `-c, --config PATH` - Configuration file
- `-f, --format [syslog-ng]` - Output format
- `-o, --output PATH` - Output file (default: stdout)

---

## Inputs

Inputs define where the forwarder receives syslog messages.

### UDP Input
Stateless, fire-and-forget delivery.

```yaml
inputs:
  - name: udp-main
    protocol: udp
    address: "0.0.0.0:514"
```

### TCP Input
Connection-oriented with reliable delivery.

```yaml
inputs:
  - name: tcp-main
    protocol: tcp
    address: "0.0.0.0:514"
```

### Multiple Inputs
Listen on multiple ports/protocols simultaneously:

```yaml
inputs:
  - name: udp-514
    protocol: udp
    address: "0.0.0.0:514"

  - name: tcp-514
    protocol: tcp
    address: "0.0.0.0:514"

  - name: udp-1514
    protocol: udp
    address: "0.0.0.0:1514"
```

### Non-Privileged Ports
For testing without root, use ports above 1024:

```yaml
inputs:
  - name: udp-5514
    protocol: udp
    address: "0.0.0.0:5514"
```

---

## Filters

Filters route messages based on criteria. **First match wins**.

### Match Criteria

#### By Facility
```yaml
filters:
  - name: auth-logs
    match:
      facility: [auth, authpriv]
    destinations: [siem]
```

Available facilities:
`kern`, `user`, `mail`, `daemon`, `auth`, `syslog`, `lpr`, `news`, `uucp`, `cron`, `authpriv`, `ftp`, `ntp`, `audit`, `alert`, `clock`, `local0`-`local7`

#### By Severity
```yaml
filters:
  - name: errors
    match:
      severity: [err, crit, alert, emerg]
    destinations: [alerting]
```

Available severities (highest to lowest):
`emerg`, `alert`, `crit`, `err`, `warning`, `notice`, `info`, `debug`

#### By Hostname Pattern
```yaml
filters:
  - name: web-servers
    match:
      hostname_pattern: "^web-.*"
    destinations: [web-logs]
```

#### By Message Content
```yaml
filters:
  - name: failed-logins
    match:
      message_pattern: "Failed password|authentication failure"
    destinations: [security]
```

#### Combined Criteria
All criteria must match (AND logic):

```yaml
filters:
  - name: critical-auth
    match:
      facility: [auth, authpriv]
      severity: [crit, alert, emerg]
      hostname_pattern: "^prod-.*"
    destinations: [siem, pagerduty]
```

### Filter Actions

#### Forward (default)
```yaml
filters:
  - name: forward-all
    destinations: [central]
```

#### Drop
```yaml
filters:
  - name: drop-debug
    match:
      severity: [debug]
    action: drop
```

### Catch-All Filter
Always place at the end (no `match` = matches everything):

```yaml
filters:
  - name: specific-rule
    match:
      facility: [auth]
    destinations: [siem]

  - name: default  # Catch-all
    destinations: [central]
```

### Multi-Destination Routing
```yaml
filters:
  - name: critical-alerts
    match:
      severity: [crit, alert, emerg]
    destinations: [siem, pagerduty, central]
```

---

## Transformations

Transformations modify messages before forwarding.

### Define Transforms
```yaml
transforms:
  - name: anonymize-ip
    mask_patterns:
      - pattern: "\\b\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\b"
        replacement: "x.x.x.x"
```

### Apply to Filters
```yaml
filters:
  - name: external-forward
    transforms: [anonymize-ip, mask-secrets]
    destinations: [external-siem]
```

### Available Operations

#### Remove Fields
```yaml
transforms:
  - name: strip-metadata
    remove_fields: [proc_id, structured_data, msg_id]
```

Removable fields: `hostname`, `app_name`, `proc_id`, `msg_id`, `structured_data`

#### Set Fields
```yaml
transforms:
  - name: rewrite-hostname
    set_fields:
      hostname: "forwarded-logs"
      app_name: "syslog-fwd"
```

#### Message Replace (regex)
```yaml
transforms:
  - name: normalize-whitespace
    message_replace:
      pattern: "\\s+"
      replacement: " "
```

#### Mask Patterns
```yaml
transforms:
  - name: mask-sensitive
    mask_patterns:
      # Mask IP addresses
      - pattern: "\\b\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\b"
        replacement: "x.x.x.x"

      # Mask email addresses
      - pattern: "\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{2,}\\b"
        replacement: "***@***.***"

      # Mask passwords/tokens
      - pattern: "(password|token|api_key)[\\s]*[=:][\\s]*['\"]?([^'\"\\s]+)['\"]?"
        replacement: "\\1=***REDACTED***"
```

#### Add Prefix/Suffix
```yaml
transforms:
  - name: add-source-tag
    message_prefix: "[FORWARDED] "
    message_suffix: " [END]"
```

### Chaining Transforms
Multiple transforms applied in order:

```yaml
filters:
  - name: secure-forward
    transforms: [mask-secrets, anonymize-ip, add-source-tag]
    destinations: [external]
```

---

## Destinations

Destinations define where to send messages.

### UDP Destination
```yaml
destinations:
  - name: central
    protocol: udp
    address: "logs.example.com:514"
    format: rfc3164
```

### TCP Destination
```yaml
destinations:
  - name: siem
    protocol: tcp
    address: "siem.example.com:514"
    format: rfc5424
```

### Output Formats

| Format | Description |
|--------|-------------|
| `rfc3164` | Legacy BSD syslog format |
| `rfc5424` | Modern syslog format with structured data |
| `auto` | Preserve original message format |

### Retry Configuration
```yaml
destinations:
  - name: critical
    protocol: tcp
    address: "siem.example.com:514"
    retry:
      max_attempts: 5
      backoff_seconds: 2.0  # Exponential backoff
```

---

## Monitoring

### Prometheus Metrics
Enable metrics endpoint in configuration:

```yaml
service:
  metrics:
    enabled: true
    address: "0.0.0.0:9090"
```

### Available Metrics

| Metric | Type | Labels |
|--------|------|--------|
| `syslog_messages_received_total` | Counter | protocol, facility, severity |
| `syslog_messages_forwarded_total` | Counter | destination |
| `syslog_messages_dropped_total` | Counter | reason |
| `syslog_messages_parse_errors_total` | Counter | protocol |
| `syslog_destination_up` | Gauge | destination |
| `syslog_processing_latency_seconds` | Histogram | filter |
| `syslog_active_connections` | Gauge | input |

### Health Check
```bash
curl http://localhost:9090/health
# Returns: OK
```

### Prometheus Scrape Config
```yaml
scrape_configs:
  - job_name: 'syslog-fwd'
    static_configs:
      - targets: ['localhost:9090']
```

### Example Queries

```promql
# Messages received per second
rate(syslog_messages_received_total[5m])

# Forwarding success rate
rate(syslog_messages_forwarded_total[5m]) /
rate(syslog_messages_received_total[5m])

# Messages dropped by reason
sum by (reason) (rate(syslog_messages_dropped_total[5m]))

# P99 processing latency
histogram_quantile(0.99, rate(syslog_processing_latency_seconds_bucket[5m]))
```

---

## Docker Deployment

### Basic Docker Run
```bash
docker run -d \
  --name syslog-fwd \
  -p 5514:5514/udp \
  -p 5514:5514/tcp \
  -p 9090:9090 \
  -v $(pwd)/config.yaml:/etc/syslog-fwd/config.yaml \
  syslog-fwd:latest
```

### Docker Compose
```yaml
version: '3.8'

services:
  syslog-fwd:
    image: syslog-fwd:latest
    ports:
      - "5514:5514/udp"
      - "5514:5514/tcp"
      - "9090:9090"
    volumes:
      - ./config.yaml:/etc/syslog-fwd/config.yaml:ro
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9090/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### With Monitoring Stack
```yaml
version: '3.8'

services:
  syslog-fwd:
    image: syslog-fwd:latest
    ports:
      - "5514:5514/udp"
      - "5514:5514/tcp"
    volumes:
      - ./config.yaml:/etc/syslog-fwd/config.yaml:ro

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9091:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
```

---

## Troubleshooting

### Common Issues

#### Port Already in Use
```
Error: Address already in use
```

**Solution**: Check for existing processes:
```bash
lsof -i :514
# or use a different port
```

#### Permission Denied (port < 1024)
```
Error: Permission denied
```

**Solution**: Use ports above 1024 or run with elevated privileges:
```bash
# Option 1: Use non-privileged port
address: "0.0.0.0:5514"

# Option 2: Use capabilities (Linux)
sudo setcap 'cap_net_bind_service=+ep' $(which syslog-fwd)
```

#### Connection Refused to Destination
```
Failed to connect output: Connection refused
```

**Solution**: 
1. Verify destination is reachable: `nc -vz host port`
2. Check firewall rules
3. Verify destination service is running

#### Messages Not Forwarded
**Debug steps**:
1. Check filter rules (first match wins)
2. Enable debug logging: `log_level: debug`
3. Check metrics for dropped messages
4. Use `simulate` to test

#### High Latency
**Solution**:
1. Check destination connectivity
2. Monitor `syslog_processing_latency_seconds` metric
3. Consider UDP for lower latency requirements
4. Review transform complexity

### Debug Mode
Enable verbose logging:

```yaml
service:
  log_level: debug
```

### Testing Configuration

#### Test Filter Matching
```bash
# Send specific message types
syslog-fwd simulate -d localhost:5514 -f auth -s err -n 1

# Check logs for routing
```

#### Test Transformations
1. Send a message with sensitive data
2. Capture at destination
3. Verify masking/transformation applied

#### Load Testing
```bash
# Burst test
syslog-fwd simulate -d localhost:5514 -n 10000 -r 1000

# Monitor metrics during test
curl http://localhost:9090/metrics | grep syslog_
```

### Log Analysis
Look for these log entries:

```
# Successful startup
INFO  Configuration loaded
INFO  UDP listener started
INFO  TCP listener started
INFO  Metrics server started
INFO  Syslog forwarder started

# Message flow
DEBUG Message dropped filter=drop-debug
DEBUG UDP send failed
WARNING Failed to forward message destination=siem
```

### Getting Help
1. Check configuration with `syslog-fwd validate`
2. Enable debug logging
3. Review Prometheus metrics
4. Check `/health` endpoint
5. Review GitHub issues
