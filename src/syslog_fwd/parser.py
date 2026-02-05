"""Syslog message parser for RFC 3164 and RFC 5424 formats."""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from .config import FACILITY_REVERSE_MAP, SEVERITY_REVERSE_MAP


@dataclass
class SyslogMessage:
    """Parsed syslog message."""

    facility: int
    severity: int
    timestamp: datetime | None
    hostname: str | None
    app_name: str | None
    proc_id: str | None
    msg_id: str | None
    structured_data: str | None
    message: str
    raw: bytes
    format: str  # "rfc3164" or "rfc5424"

    @property
    def facility_name(self) -> str:
        """Get facility name."""
        return FACILITY_REVERSE_MAP.get(self.facility, f"unknown({self.facility})")

    @property
    def severity_name(self) -> str:
        """Get severity name."""
        return SEVERITY_REVERSE_MAP.get(self.severity, f"unknown({self.severity})")

    @property
    def priority(self) -> int:
        """Calculate PRI value."""
        return (self.facility * 8) + self.severity

    def to_rfc3164(self) -> bytes:
        """Format message as RFC 3164."""
        # <PRI>TIMESTAMP HOSTNAME TAG: MESSAGE
        pri = f"<{self.priority}>"
        ts = self.timestamp.strftime("%b %d %H:%M:%S") if self.timestamp else "-"
        hostname = self.hostname or "-"
        tag = self.app_name or "-"
        if self.proc_id:
            tag = f"{tag}[{self.proc_id}]"
        return f"{pri}{ts} {hostname} {tag}: {self.message}".encode("utf-8")

    def to_rfc5424(self) -> bytes:
        """Format message as RFC 5424."""
        # <PRI>VERSION TIMESTAMP HOSTNAME APP-NAME PROCID MSGID SD MSG
        pri = f"<{self.priority}>1"
        ts = self.timestamp.isoformat() if self.timestamp else "-"
        hostname = self.hostname or "-"
        app_name = self.app_name or "-"
        proc_id = self.proc_id or "-"
        msg_id = self.msg_id or "-"
        sd = self.structured_data or "-"
        return f"{pri} {ts} {hostname} {app_name} {proc_id} {msg_id} {sd} {self.message}".encode(
            "utf-8"
        )


class SyslogParser:
    """Parser for syslog messages supporting RFC 3164 and RFC 5424."""

    # RFC 5424: <PRI>VERSION SP TIMESTAMP SP HOSTNAME SP APP-NAME SP PROCID SP MSGID SP SD MSG
    RFC5424_PATTERN: ClassVar[re.Pattern] = re.compile(
        rb"<(\d{1,3})>1 "  # PRI and VERSION
        rb"(\S+) "  # TIMESTAMP
        rb"(\S+) "  # HOSTNAME
        rb"(\S+) "  # APP-NAME
        rb"(\S+) "  # PROCID
        rb"(\S+) "  # MSGID
        rb"(\[.*?\]|-) ?"  # STRUCTURED-DATA (simplified)
        rb"(.*)$",  # MSG
        re.DOTALL,
    )

    # RFC 3164: <PRI>TIMESTAMP HOSTNAME TAG: MSG
    # Timestamp: Mmm dd hh:mm:ss
    RFC3164_PATTERN: ClassVar[re.Pattern] = re.compile(
        rb"<(\d{1,3})>"  # PRI
        rb"([A-Z][a-z]{2} [ \d]\d \d{2}:\d{2}:\d{2}) "  # TIMESTAMP
        rb"(\S+) "  # HOSTNAME
        rb"(.*)$",  # TAG + MSG
        re.DOTALL,
    )

    # Simple pattern for messages with just PRI
    SIMPLE_PATTERN: ClassVar[re.Pattern] = re.compile(
        rb"<(\d{1,3})>(.*)$",
        re.DOTALL,
    )

    # Month name mapping
    MONTHS: ClassVar[dict[str, int]] = {
        "Jan": 1,
        "Feb": 2,
        "Mar": 3,
        "Apr": 4,
        "May": 5,
        "Jun": 6,
        "Jul": 7,
        "Aug": 8,
        "Sep": 9,
        "Oct": 10,
        "Nov": 11,
        "Dec": 12,
    }

    @classmethod
    def parse(cls, data: bytes) -> SyslogMessage:
        """Parse a syslog message.

        Attempts RFC 5424 first, then RFC 3164, then falls back to simple parsing.

        Args:
            data: Raw syslog message bytes.

        Returns:
            Parsed SyslogMessage.

        Raises:
            ValueError: If the message cannot be parsed.
        """
        # Remove trailing newlines
        data = data.rstrip(b"\r\n")

        # Try RFC 5424 first
        match = cls.RFC5424_PATTERN.match(data)
        if match:
            return cls._parse_rfc5424(match, data)

        # Try RFC 3164
        match = cls.RFC3164_PATTERN.match(data)
        if match:
            return cls._parse_rfc3164(match, data)

        # Fall back to simple parsing
        match = cls.SIMPLE_PATTERN.match(data)
        if match:
            return cls._parse_simple(match, data)

        raise ValueError(f"Unable to parse syslog message: {data[:100]!r}")

    @classmethod
    def _parse_priority(cls, pri_str: bytes) -> tuple[int, int]:
        """Parse PRI value into facility and severity."""
        pri = int(pri_str)
        if pri < 0 or pri > 191:
            raise ValueError(f"Invalid PRI value: {pri}")
        facility = pri >> 3
        severity = pri & 0x07
        return facility, severity

    @classmethod
    def _parse_rfc5424(cls, match: re.Match, raw: bytes) -> SyslogMessage:
        """Parse RFC 5424 message."""
        pri, ts, hostname, app_name, proc_id, msg_id, sd, msg = match.groups()
        facility, severity = cls._parse_priority(pri)

        # Parse timestamp
        ts_str = ts.decode("utf-8", errors="replace")
        timestamp = None
        if ts_str != "-":
            try:
                # Handle various ISO 8601 formats
                timestamp = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except ValueError:
                pass

        # Decode fields
        def decode_field(b: bytes) -> str | None:
            s = b.decode("utf-8", errors="replace")
            return None if s == "-" else s

        return SyslogMessage(
            facility=facility,
            severity=severity,
            timestamp=timestamp,
            hostname=decode_field(hostname),
            app_name=decode_field(app_name),
            proc_id=decode_field(proc_id),
            msg_id=decode_field(msg_id),
            structured_data=decode_field(sd),
            message=msg.decode("utf-8", errors="replace"),
            raw=raw,
            format="rfc5424",
        )

    @classmethod
    def _parse_rfc3164(cls, match: re.Match, raw: bytes) -> SyslogMessage:
        """Parse RFC 3164 message."""
        pri, ts, hostname, tag_msg = match.groups()
        facility, severity = cls._parse_priority(pri)

        # Parse timestamp (Mmm dd hh:mm:ss)
        ts_str = ts.decode("utf-8", errors="replace")
        timestamp = None
        try:
            # Parse: "Jan  5 12:34:56" or "Jan 15 12:34:56"
            parts = ts_str.split()
            month = cls.MONTHS.get(parts[0], 1)
            day = int(parts[1])
            time_parts = parts[2].split(":")
            hour, minute, second = int(time_parts[0]), int(time_parts[1]), int(time_parts[2])
            # Use current year since RFC 3164 doesn't include year
            year = datetime.now().year
            timestamp = datetime(year, month, day, hour, minute, second)
        except (IndexError, ValueError):
            pass

        # Parse TAG and MSG
        tag_msg_str = tag_msg.decode("utf-8", errors="replace")
        app_name = None
        proc_id = None
        message = tag_msg_str

        # Try to extract TAG[PID]: MSG
        tag_match = re.match(r"^(\S+?)(?:\[(\d+)\])?:\s*(.*)$", tag_msg_str, re.DOTALL)
        if tag_match:
            app_name = tag_match.group(1)
            proc_id = tag_match.group(2)
            message = tag_match.group(3)

        return SyslogMessage(
            facility=facility,
            severity=severity,
            timestamp=timestamp,
            hostname=hostname.decode("utf-8", errors="replace"),
            app_name=app_name,
            proc_id=proc_id,
            msg_id=None,
            structured_data=None,
            message=message,
            raw=raw,
            format="rfc3164",
        )

    @classmethod
    def _parse_simple(cls, match: re.Match, raw: bytes) -> SyslogMessage:
        """Parse simple message with just PRI."""
        pri, msg = match.groups()
        facility, severity = cls._parse_priority(pri)

        return SyslogMessage(
            facility=facility,
            severity=severity,
            timestamp=datetime.now(),
            hostname=None,
            app_name=None,
            proc_id=None,
            msg_id=None,
            structured_data=None,
            message=msg.decode("utf-8", errors="replace"),
            raw=raw,
            format="rfc3164",
        )
