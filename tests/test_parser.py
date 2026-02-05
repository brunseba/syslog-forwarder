"""Tests for syslog message parser."""

import pytest
from datetime import datetime

from syslog_fwd.parser import SyslogParser, SyslogMessage


class TestSyslogParser:
    """Tests for SyslogParser class."""

    def test_parse_rfc5424_basic(self):
        """Test parsing a basic RFC 5424 message."""
        msg = b"<34>1 2024-01-15T12:30:45.123Z hostname app 1234 ID47 - Test message"
        result = SyslogParser.parse(msg)

        assert result.facility == 4  # auth
        assert result.severity == 2  # crit
        assert result.hostname == "hostname"
        assert result.app_name == "app"
        assert result.proc_id == "1234"
        assert result.msg_id == "ID47"
        assert result.message == "Test message"
        assert result.format == "rfc5424"

    def test_parse_rfc5424_with_structured_data(self):
        """Test parsing RFC 5424 with structured data."""
        msg = b"<165>1 2024-01-15T12:30:45Z host app - - [exampleSDID@32473 key=\"value\"] Message"
        result = SyslogParser.parse(msg)

        assert result.facility == 20  # local4
        assert result.severity == 5  # notice
        assert result.structured_data == '[exampleSDID@32473 key="value"]'
        assert result.message == "Message"

    def test_parse_rfc5424_nil_values(self):
        """Test parsing RFC 5424 with nil values."""
        msg = b"<14>1 - - - - - - Just a message"
        result = SyslogParser.parse(msg)

        assert result.facility == 1  # user
        assert result.severity == 6  # info
        assert result.hostname is None
        assert result.app_name is None
        assert result.proc_id is None
        assert result.message == "Just a message"

    def test_parse_rfc3164_basic(self):
        """Test parsing a basic RFC 3164 message."""
        msg = b"<34>Jan 15 12:30:45 myhost sshd[1234]: Connection from 192.168.1.1"
        result = SyslogParser.parse(msg)

        assert result.facility == 4  # auth
        assert result.severity == 2  # crit
        assert result.hostname == "myhost"
        assert result.app_name == "sshd"
        assert result.proc_id == "1234"
        assert result.message == "Connection from 192.168.1.1"
        assert result.format == "rfc3164"

    def test_parse_rfc3164_no_pid(self):
        """Test parsing RFC 3164 without PID."""
        msg = b"<13>Feb  5 08:30:00 server kernel: Some kernel message"
        result = SyslogParser.parse(msg)

        assert result.facility == 1  # user
        assert result.severity == 5  # notice
        assert result.hostname == "server"
        assert result.app_name == "kernel"
        assert result.proc_id is None

    def test_parse_simple_message(self):
        """Test parsing a simple message with just PRI."""
        msg = b"<14>Simple message without standard format"
        result = SyslogParser.parse(msg)

        assert result.facility == 1  # user
        assert result.severity == 6  # info
        assert result.message == "Simple message without standard format"

    def test_parse_priority_calculation(self):
        """Test priority value parsing."""
        # PRI = facility * 8 + severity
        # facility=4 (auth), severity=2 (crit) = 34
        msg = b"<34>1 - - - - - - test"
        result = SyslogParser.parse(msg)

        assert result.priority == 34
        assert result.facility == 4
        assert result.severity == 2

    def test_parse_invalid_priority(self):
        """Test parsing with invalid priority raises error."""
        msg = b"<999>Invalid priority"
        with pytest.raises(ValueError):
            SyslogParser.parse(msg)

    def test_parse_invalid_message(self):
        """Test parsing completely invalid message raises error."""
        msg = b"No priority prefix at all"
        with pytest.raises(ValueError):
            SyslogParser.parse(msg)

    def test_facility_name_property(self):
        """Test facility_name property."""
        msg = b"<34>1 - - - - - - test"  # facility=4 (auth)
        result = SyslogParser.parse(msg)
        assert result.facility_name == "auth"

    def test_severity_name_property(self):
        """Test severity_name property."""
        msg = b"<34>1 - - - - - - test"  # severity=2 (crit)
        result = SyslogParser.parse(msg)
        assert result.severity_name == "crit"

    def test_to_rfc3164_output(self):
        """Test formatting message as RFC 3164."""
        msg = b"<34>1 2024-01-15T12:30:45Z hostname app 1234 - - Test message"
        result = SyslogParser.parse(msg)
        output = result.to_rfc3164()

        assert output.startswith(b"<34>")
        assert b"hostname" in output
        assert b"app[1234]:" in output
        assert b"Test message" in output

    def test_to_rfc5424_output(self):
        """Test formatting message as RFC 5424."""
        msg = b"<34>Jan 15 12:30:45 hostname app[1234]: Test message"
        result = SyslogParser.parse(msg)
        output = result.to_rfc5424()

        assert output.startswith(b"<34>1")
        assert b"hostname" in output
        assert b"Test message" in output

    def test_parse_strips_trailing_newlines(self):
        """Test that trailing newlines are stripped."""
        msg = b"<14>1 - - - - - - Test\n"
        result = SyslogParser.parse(msg)
        assert result.message == "Test"

        msg = b"<14>1 - - - - - - Test\r\n"
        result = SyslogParser.parse(msg)
        assert result.message == "Test"
