"""Configuration models for syslog-fwd."""

import os
import re
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class Protocol(str, Enum):
    """Supported network protocols."""

    UDP = "udp"
    TCP = "tcp"
    TLS = "tls"


class SyslogFormat(str, Enum):
    """Syslog message formats."""

    RFC3164 = "rfc3164"
    RFC5424 = "rfc5424"
    AUTO = "auto"


class Facility(str, Enum):
    """Syslog facilities (RFC 5424)."""

    KERN = "kern"
    USER = "user"
    MAIL = "mail"
    DAEMON = "daemon"
    AUTH = "auth"
    SYSLOG = "syslog"
    LPR = "lpr"
    NEWS = "news"
    UUCP = "uucp"
    CRON = "cron"
    AUTHPRIV = "authpriv"
    FTP = "ftp"
    NTP = "ntp"
    AUDIT = "audit"
    ALERT = "alert"
    CLOCK = "clock"
    LOCAL0 = "local0"
    LOCAL1 = "local1"
    LOCAL2 = "local2"
    LOCAL3 = "local3"
    LOCAL4 = "local4"
    LOCAL5 = "local5"
    LOCAL6 = "local6"
    LOCAL7 = "local7"


# Facility name to numeric value mapping
FACILITY_MAP: dict[str, int] = {
    "kern": 0,
    "user": 1,
    "mail": 2,
    "daemon": 3,
    "auth": 4,
    "syslog": 5,
    "lpr": 6,
    "news": 7,
    "uucp": 8,
    "cron": 9,
    "authpriv": 10,
    "ftp": 11,
    "ntp": 12,
    "audit": 13,
    "alert": 14,
    "clock": 15,
    "local0": 16,
    "local1": 17,
    "local2": 18,
    "local3": 19,
    "local4": 20,
    "local5": 21,
    "local6": 22,
    "local7": 23,
}

FACILITY_REVERSE_MAP: dict[int, str] = {v: k for k, v in FACILITY_MAP.items()}


class Severity(str, Enum):
    """Syslog severities (RFC 5424)."""

    EMERG = "emerg"
    ALERT = "alert"
    CRIT = "crit"
    ERR = "err"
    WARNING = "warning"
    NOTICE = "notice"
    INFO = "info"
    DEBUG = "debug"


# Severity name to numeric value mapping
SEVERITY_MAP: dict[str, int] = {
    "emerg": 0,
    "alert": 1,
    "crit": 2,
    "err": 3,
    "warning": 4,
    "notice": 5,
    "info": 6,
    "debug": 7,
}

SEVERITY_REVERSE_MAP: dict[int, str] = {v: k for k, v in SEVERITY_MAP.items()}


class InputConfig(BaseModel):
    """Configuration for a syslog input listener."""

    name: str = Field(..., description="Unique name for this input")
    protocol: Protocol = Field(default=Protocol.UDP, description="Protocol to listen on")
    address: str = Field(default="0.0.0.0:514", description="Address to bind to (host:port)")
    format: SyslogFormat = Field(default=SyslogFormat.AUTO, description="Expected message format")

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        """Validate address format (host:port)."""
        if ":" not in v:
            raise ValueError("Address must be in format 'host:port'")
        host, port_str = v.rsplit(":", 1)
        try:
            port = int(port_str)
            if not 1 <= port <= 65535:
                raise ValueError("Port must be between 1 and 65535")
        except ValueError as e:
            raise ValueError(f"Invalid port: {e}") from e
        return v

    @property
    def host(self) -> str:
        """Extract host from address."""
        return self.address.rsplit(":", 1)[0]

    @property
    def port(self) -> int:
        """Extract port from address."""
        return int(self.address.rsplit(":", 1)[1])


class FilterMatch(BaseModel):
    """Match criteria for a filter rule."""

    facility: list[Facility] | None = Field(default=None, description="Match these facilities")
    severity: list[Severity] | None = Field(default=None, description="Match these severities")
    hostname_pattern: str | None = Field(default=None, description="Regex pattern for hostname")
    message_pattern: str | None = Field(default=None, description="Regex pattern for message")

    @field_validator("hostname_pattern", "message_pattern")
    @classmethod
    def validate_regex(cls, v: str | None) -> str | None:
        """Validate regex patterns."""
        if v is not None:
            try:
                re.compile(v)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern: {e}") from e
        return v


class ReplaceConfig(BaseModel):
    """Configuration for regex replacement in messages."""

    pattern: str = Field(..., description="Regex pattern to match")
    replacement: str = Field(default="", description="Replacement string (supports \\1, \\2)")

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, v: str) -> str:
        """Validate regex pattern."""
        try:
            re.compile(v)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}") from e
        return v


class MaskConfig(BaseModel):
    """Configuration for masking sensitive data."""

    pattern: str = Field(..., description="Regex pattern to match sensitive data")
    replacement: str = Field(default="***MASKED***", description="Replacement text")

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, v: str) -> str:
        """Validate regex pattern."""
        try:
            re.compile(v)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}") from e
        return v


class TransformConfig(BaseModel):
    """Configuration for message transformation."""

    name: str = Field(..., description="Unique name for this transformation")
    match_pattern: str | None = Field(
        default=None, description="Only apply to messages matching this regex"
    )

    # Field operations
    remove_fields: list[str] | None = Field(
        default=None,
        description="Fields to remove: hostname, app_name, proc_id, msg_id, structured_data",
    )
    set_fields: dict[str, str] | None = Field(
        default=None, description="Fields to set to specific values"
    )

    # Message content operations
    message_replace: ReplaceConfig | None = Field(
        default=None, description="Regex replacement in message content"
    )
    mask_patterns: list[MaskConfig] | None = Field(
        default=None, description="Patterns to mask (e.g., passwords, IPs)"
    )
    message_prefix: str | None = Field(default=None, description="Prepend to message")
    message_suffix: str | None = Field(default=None, description="Append to message")

    @field_validator("match_pattern")
    @classmethod
    def validate_match_pattern(cls, v: str | None) -> str | None:
        """Validate match pattern."""
        if v is not None:
            try:
                re.compile(v)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern: {e}") from e
        return v

    @field_validator("remove_fields")
    @classmethod
    def validate_remove_fields(cls, v: list[str] | None) -> list[str] | None:
        """Validate remove_fields values."""
        valid_fields = {"hostname", "app_name", "proc_id", "msg_id", "structured_data"}
        if v:
            for field in v:
                if field not in valid_fields:
                    raise ValueError(
                        f"Invalid field '{field}'. Valid: {', '.join(valid_fields)}"
                    )
        return v


class FilterConfig(BaseModel):
    """Configuration for a filter rule."""

    name: str = Field(..., description="Unique name for this filter")
    match: FilterMatch | None = Field(default=None, description="Match criteria")
    action: Literal["forward", "drop"] = Field(default="forward", description="Action to take")
    destinations: list[str] | None = Field(
        default=None, description="Destination names to forward to"
    )
    transforms: list[str] | None = Field(
        default=None, description="Transform names to apply before forwarding"
    )

    @model_validator(mode="after")
    def validate_filter(self) -> "FilterConfig":
        """Validate filter configuration."""
        if self.action == "forward" and not self.destinations:
            raise ValueError("Filter with 'forward' action must specify destinations")
        if self.action == "drop" and self.destinations:
            raise ValueError("Filter with 'drop' action should not have destinations")
        return self


class RetryConfig(BaseModel):
    """Retry configuration for destinations."""

    max_attempts: int = Field(default=3, ge=1, le=10, description="Maximum retry attempts")
    backoff_seconds: float = Field(default=1.0, ge=0.1, le=60.0, description="Initial backoff")


class DestinationConfig(BaseModel):
    """Configuration for a forwarding destination."""

    name: str = Field(..., description="Unique name for this destination")
    protocol: Protocol = Field(default=Protocol.UDP, description="Protocol to use")
    address: str = Field(..., description="Destination address (host:port)")
    format: SyslogFormat = Field(default=SyslogFormat.RFC5424, description="Output format")
    retry: RetryConfig = Field(default_factory=RetryConfig, description="Retry configuration")

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        """Validate address format."""
        if ":" not in v:
            raise ValueError("Address must be in format 'host:port'")
        _, port_str = v.rsplit(":", 1)
        try:
            port = int(port_str)
            if not 1 <= port <= 65535:
                raise ValueError("Port must be between 1 and 65535")
        except ValueError as e:
            raise ValueError(f"Invalid port: {e}") from e
        return v

    @property
    def host(self) -> str:
        """Extract host from address."""
        return self.address.rsplit(":", 1)[0]

    @property
    def port(self) -> int:
        """Extract port from address."""
        return int(self.address.rsplit(":", 1)[1])


class MetricsConfig(BaseModel):
    """Prometheus metrics configuration."""

    enabled: bool = Field(default=True, description="Enable metrics endpoint")
    address: str = Field(default="0.0.0.0:9090", description="Metrics endpoint address")

    @property
    def host(self) -> str:
        """Extract host from address."""
        return self.address.rsplit(":", 1)[0]

    @property
    def port(self) -> int:
        """Extract port from address."""
        return int(self.address.rsplit(":", 1)[1])


class ServiceConfig(BaseModel):
    """Service-level configuration."""

    log_level: Literal["debug", "info", "warning", "error"] = Field(
        default="info", description="Logging level"
    )
    metrics: MetricsConfig = Field(default_factory=MetricsConfig, description="Metrics config")


class Config(BaseModel):
    """Root configuration for syslog-fwd."""

    version: Annotated[str, Field(pattern=r"^\d+$")] = Field(
        default="1", description="Config schema version"
    )
    inputs: list[InputConfig] = Field(default_factory=list, description="Input listeners")
    transforms: list[TransformConfig] = Field(
        default_factory=list, description="Message transformations"
    )
    filters: list[FilterConfig] = Field(default_factory=list, description="Filter rules")
    destinations: list[DestinationConfig] = Field(
        default_factory=list, description="Forward destinations"
    )
    service: ServiceConfig = Field(default_factory=ServiceConfig, description="Service settings")

    @model_validator(mode="after")
    def validate_references(self) -> "Config":
        """Validate that all referenced destinations and transforms exist."""
        dest_names = {d.name for d in self.destinations}
        transform_names = {t.name for t in self.transforms}

        for f in self.filters:
            # Validate destination references
            if f.destinations:
                for dest in f.destinations:
                    if dest not in dest_names:
                        raise ValueError(
                            f"Filter '{f.name}' references unknown destination '{dest}'"
                        )
            # Validate transform references
            if f.transforms:
                for transform in f.transforms:
                    if transform not in transform_names:
                        raise ValueError(
                            f"Filter '{f.name}' references unknown transform '{transform}'"
                        )
        return self


def _substitute_env_vars(content: str) -> str:
    """Substitute ${VAR} and ${VAR:-default} patterns with environment variables."""
    pattern = r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}"

    def replace(match: re.Match) -> str:
        var_name = match.group(1)
        default = match.group(2)
        value = os.environ.get(var_name)
        if value is not None:
            return value
        if default is not None:
            return default
        return match.group(0)  # Keep original if no value and no default

    return re.sub(pattern, replace, content)


def load_config(path: str | Path) -> Config:
    """Load configuration from a YAML file.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        Validated Config object.

    Raises:
        FileNotFoundError: If the config file doesn't exist.
        ValueError: If the config is invalid.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    content = path.read_text()
    content = _substitute_env_vars(content)

    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML: {e}") from e

    if data is None:
        data = {}

    return Config.model_validate(data)
