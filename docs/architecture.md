# Syslog Forwarder - Architecture

## Overview
Syslog-fwd is an async Python service that receives, filters, transforms, and forwards syslog messages. Built on asyncio for high-performance message processing.

## High-Level Architecture

```mermaid
flowchart TB
    subgraph Sources["Syslog Sources"]
        S1[Servers]
        S2[Network Devices]
        S3[Applications]
    end

    subgraph syslog-fwd["syslog-fwd"]
        subgraph Inputs["Inputs"]
            UDP_IN[UDP Listener<br/>:5514]
            TCP_IN[TCP Listener<br/>:5514]
        end

        subgraph Core["Processing Core"]
            Parser[SyslogParser]
            FE[FilterEngine]
            T[Transformer]
        end

        subgraph Outputs["Outputs"]
            UDP_OUT[UDP Forwarder]
            TCP_OUT[TCP Forwarder]
        end

        subgraph Management["Management"]
            CLI[CLI]
            M[Metrics :9090]
            H[Health /health]
        end
    end

    subgraph Destinations["Destinations"]
        SIEM[SIEM]
        Central[Central Logs]
        Alert[Alerting]
    end

    subgraph Monitoring["Monitoring"]
        P[Prometheus]
        G[Grafana]
    end

    S1 & S2 & S3 -->|UDP/TCP| Inputs
    UDP_IN & TCP_IN --> Parser
    Parser --> FE
    FE --> T
    T --> Outputs
    UDP_OUT --> SIEM & Central
    TCP_OUT --> SIEM & Alert
    M --> P --> G
```

## Component Model

```mermaid
classDiagram
    class SyslogForwarder {
        +config: Config
        +inputs: list~BaseInput~
        +outputs: dict~BaseOutput~
        +filter_engine: FilterEngine
        +transformer: MessageTransformer
        +start() async
        +stop() async
        +run_forever() async
        -_handle_message(message) async
    }

    class BaseInput {
        <<abstract>>
        +config: InputConfig
        +handler: MessageHandler
        +start() async
        +stop() async
    }

    class UDPInput {
        -_transport: DatagramTransport
        -_protocol: UDPProtocol
    }

    class TCPInput {
        -_server: Server
        -_handle_client() async
        -_extract_message() bytes
    }

    class BaseOutput {
        <<abstract>>
        +config: DestinationConfig
        +connected: bool
        +connect() async
        +disconnect() async
        +send(message) async bool
        +send_with_retry(message) async bool
    }

    class UDPOutput {
        -_socket: socket
    }

    class TCPOutput {
        -_reader: StreamReader
        -_writer: StreamWriter
        -_lock: Lock
    }

    class FilterEngine {
        +filters: list~FilterConfig~
        -_compiled_patterns: dict
        +evaluate(message) FilterResult
        +reload(filters)
    }

    class MessageTransformer {
        +transforms: list~TransformConfig~
        -_transforms_by_name: dict
        -_compiled_patterns: dict
        +transform(message, names) SyslogMessage
        +reload(transforms)
    }

    class SyslogParser {
        +parse(data) SyslogMessage$
        -_parse_rfc5424() SyslogMessage$
        -_parse_rfc3164() SyslogMessage$
        -_parse_simple() SyslogMessage$
    }

    class SyslogMessage {
        +facility: int
        +severity: int
        +timestamp: datetime
        +hostname: str
        +app_name: str
        +proc_id: str
        +msg_id: str
        +structured_data: str
        +message: str
        +raw: bytes
        +format: str
        +to_rfc3164() bytes
        +to_rfc5424() bytes
    }

    BaseInput <|-- UDPInput
    BaseInput <|-- TCPInput
    BaseOutput <|-- UDPOutput
    BaseOutput <|-- TCPOutput

    SyslogForwarder *-- BaseInput
    SyslogForwarder *-- BaseOutput
    SyslogForwarder *-- FilterEngine
    SyslogForwarder *-- MessageTransformer

    BaseInput ..> SyslogParser : uses
    SyslogParser ..> SyslogMessage : creates
    FilterEngine ..> SyslogMessage : evaluates
    MessageTransformer ..> SyslogMessage : transforms
    BaseOutput ..> SyslogMessage : sends
```

## Data Flow

```mermaid
sequenceDiagram
    participant S as Syslog Source
    participant I as Input (UDP/TCP)
    participant P as SyslogParser
    participant FE as FilterEngine
    participant T as Transformer
    participant O as Output
    participant D as Destination
    participant M as Metrics

    S->>I: Raw message (bytes)
    I->>P: parse(data)
    P-->>I: SyslogMessage
    I->>M: MESSAGES_RECEIVED++

    I->>FE: evaluate(message)
    FE->>M: PROCESSING_LATENCY

    alt Filter: drop
        FE-->>I: FilterResult(action=drop)
        I->>M: MESSAGES_DROPPED++
    else Filter: forward
        FE-->>I: FilterResult(destinations, transforms)

        opt Has transforms
            I->>T: transform(message, names)
            T-->>I: transformed_message
        end

        loop Each destination
            I->>O: send_with_retry(message)
            O->>D: formatted message
            D-->>O: ack (TCP only)
            O->>M: MESSAGES_FORWARDED++
        end
    end
```

## Component Details

### CLI (`cli.py`)
Entry point using Click framework.

| Command | Description |
|---------|-------------|
| `run` | Start the forwarder service |
| `validate` | Validate configuration file |
| `simulate` | Test message against filters |
| `init` | Generate example configuration |
| `export` | Convert config to syslog-ng format |

### Config (`config.py`)
Pydantic models for configuration validation.

```mermaid
classDiagram
    class Config {
        +inputs: list~InputConfig~
        +filters: list~FilterConfig~
        +destinations: list~DestinationConfig~
        +transforms: list~TransformConfig~
        +service: ServiceConfig
    }

    class InputConfig {
        +name: str
        +protocol: Protocol
        +host: str
        +port: int
    }

    class FilterConfig {
        +name: str
        +match: MatchConfig
        +action: str
        +destinations: list~str~
        +transforms: list~str~
    }

    class DestinationConfig {
        +name: str
        +protocol: Protocol
        +host: str
        +port: int
        +format: SyslogFormat
        +retry: RetryConfig
    }

    class TransformConfig {
        +name: str
        +remove_fields: list~str~
        +set_fields: dict
        +message_replace: ReplaceConfig
        +mask_patterns: list~MaskConfig~
        +message_prefix: str
        +message_suffix: str
    }

    Config *-- InputConfig
    Config *-- FilterConfig
    Config *-- DestinationConfig
    Config *-- TransformConfig
```

### Parser (`parser.py`)
Parses raw syslog messages into structured `SyslogMessage` objects.

Supported formats:
- **RFC 5424**: Modern syslog format with structured data
- **RFC 3164**: Legacy BSD syslog format
- **Simple**: Minimal format with PRI only

### Inputs (`inputs.py`)
Async listeners for receiving syslog messages.

| Class | Protocol | Features |
|-------|----------|----------|
| `UDPInput` | UDP | Stateless, fire-and-forget |
| `TCPInput` | TCP | Connection tracking, RFC 6587 framing |

### Filters (`filters.py`)
First-match-wins filter engine.

Match criteria:
- Facility (kern, user, mail, etc.)
- Severity (emerg, alert, crit, etc.)
- Hostname pattern (regex)
- Message pattern (regex)

### Transformer (`transformer.py`)
Message transformation operations.

| Operation | Description |
|-----------|-------------|
| `remove_fields` | Remove specific fields |
| `set_fields` | Set fields to values |
| `message_replace` | Regex replacement in message |
| `mask_patterns` | Mask sensitive data |
| `message_prefix/suffix` | Add prefix/suffix to message |

### Outputs (`outputs.py`)
Async forwarders with retry logic.

| Class | Protocol | Features |
|-------|----------|----------|
| `UDPOutput` | UDP | Non-blocking socket |
| `TCPOutput` | TCP | Connection pooling, timeout |

### Metrics (`metrics.py`)
Prometheus metrics exported at `/metrics`.

| Metric | Type | Description |
|--------|------|-------------|
| `syslog_messages_received_total` | Counter | Messages received by protocol/facility/severity |
| `syslog_messages_forwarded_total` | Counter | Messages forwarded by destination |
| `syslog_messages_dropped_total` | Counter | Messages dropped by reason |
| `syslog_processing_latency_seconds` | Histogram | Filter evaluation time |
| `syslog_destination_up` | Gauge | Destination health (0/1) |
| `syslog_active_connections` | Gauge | Active TCP connections |

## External Interfaces

```mermaid
flowchart LR
    subgraph Inputs
        UDP514[UDP :5514]
        TCP514[TCP :5514]
    end

    subgraph syslog-fwd
        Core[Forwarder Core]
    end

    subgraph Management
        HTTP[HTTP :9090]
    end

    subgraph Outputs
        UDPOut[UDP destinations]
        TCPOut[TCP destinations]
    end

    UDP514 --> Core
    TCP514 --> Core
    Core --> UDPOut
    Core --> TCPOut
    Core --> HTTP

    HTTP --> |/metrics| Prometheus
    HTTP --> |/health| Healthcheck
```

## Technology Stack

| Component | Technology |
|-----------|------------|
| Runtime | Python 3.10+ |
| Async | asyncio |
| Config | Pydantic |
| CLI | Click |
| Logging | structlog |
| Metrics | prometheus_client |
| Package | uv |
