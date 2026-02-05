"""Prometheus metrics for syslog-fwd."""

from prometheus_client import Counter, Gauge, Histogram

# Message counters
MESSAGES_RECEIVED = Counter(
    "syslog_messages_received_total",
    "Total number of syslog messages received",
    ["protocol", "facility", "severity"],
)

MESSAGES_FORWARDED = Counter(
    "syslog_messages_forwarded_total",
    "Total number of syslog messages forwarded",
    ["destination"],
)

MESSAGES_DROPPED = Counter(
    "syslog_messages_dropped_total",
    "Total number of syslog messages dropped",
    ["reason"],
)

MESSAGES_PARSE_ERRORS = Counter(
    "syslog_messages_parse_errors_total",
    "Total number of message parse errors",
    ["protocol"],
)

# Destination status
DESTINATION_UP = Gauge(
    "syslog_destination_up",
    "Whether a destination is reachable (1=up, 0=down)",
    ["destination"],
)

# Processing latency
PROCESSING_LATENCY = Histogram(
    "syslog_processing_latency_seconds",
    "Time spent processing messages",
    ["filter"],
    buckets=(0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1),
)

# Connection counters
ACTIVE_CONNECTIONS = Gauge(
    "syslog_active_connections",
    "Number of active TCP connections",
    ["input"],
)
