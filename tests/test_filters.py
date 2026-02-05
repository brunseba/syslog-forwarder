"""Tests for filter engine."""

from datetime import datetime

import pytest

from syslog_fwd.config import Facility, FilterConfig, FilterMatch, Severity
from syslog_fwd.filters import FilterEngine
from syslog_fwd.parser import SyslogMessage


def make_message(
    facility: int = 1,
    severity: int = 6,
    hostname: str | None = "testhost",
    message: str = "Test message",
) -> SyslogMessage:
    """Create a test syslog message."""
    return SyslogMessage(
        facility=facility,
        severity=severity,
        timestamp=datetime.now(),
        hostname=hostname,
        app_name="test",
        proc_id="1234",
        msg_id=None,
        structured_data=None,
        message=message,
        raw=b"",
        format="rfc5424",
    )


class TestFilterEngine:
    """Tests for FilterEngine class."""

    def test_no_filters_drops_message(self):
        """Test that no filters = message dropped."""
        engine = FilterEngine([])
        result = engine.evaluate(make_message())

        assert result.matched is False
        assert result.action == "drop"
        assert result.destinations == []

    def test_catch_all_filter(self):
        """Test catch-all filter matches everything."""
        filters = [
            FilterConfig(name="default", destinations=["central"]),
        ]
        engine = FilterEngine(filters)
        result = engine.evaluate(make_message())

        assert result.matched is True
        assert result.filter_name == "default"
        assert result.action == "forward"
        assert result.destinations == ["central"]

    def test_facility_filter_match(self):
        """Test filter matching on facility."""
        filters = [
            FilterConfig(
                name="auth",
                match=FilterMatch(facility=[Facility.AUTH]),
                destinations=["siem"],
            ),
            FilterConfig(name="default", destinations=["central"]),
        ]
        engine = FilterEngine(filters)

        # Auth message (facility=4)
        result = engine.evaluate(make_message(facility=4))
        assert result.filter_name == "auth"

        # User message (facility=1)
        result = engine.evaluate(make_message(facility=1))
        assert result.filter_name == "default"

    def test_severity_filter_match(self):
        """Test filter matching on severity."""
        filters = [
            FilterConfig(
                name="errors",
                match=FilterMatch(severity=[Severity.ERR, Severity.CRIT]),
                destinations=["alerts"],
            ),
            FilterConfig(name="default", destinations=["central"]),
        ]
        engine = FilterEngine(filters)

        # Error message (severity=3)
        result = engine.evaluate(make_message(severity=3))
        assert result.filter_name == "errors"

        # Info message (severity=6)
        result = engine.evaluate(make_message(severity=6))
        assert result.filter_name == "default"

    def test_drop_filter(self):
        """Test drop filter action."""
        filters = [
            FilterConfig(
                name="drop-debug",
                match=FilterMatch(severity=[Severity.DEBUG]),
                action="drop",
            ),
            FilterConfig(name="default", destinations=["central"]),
        ]
        engine = FilterEngine(filters)

        # Debug message (severity=7)
        result = engine.evaluate(make_message(severity=7))
        assert result.filter_name == "drop-debug"
        assert result.action == "drop"
        assert result.destinations == []

    def test_first_match_wins(self):
        """Test that first matching filter wins."""
        filters = [
            FilterConfig(
                name="critical",
                match=FilterMatch(severity=[Severity.CRIT]),
                destinations=["alerts"],
            ),
            FilterConfig(
                name="auth",
                match=FilterMatch(facility=[Facility.AUTH]),
                destinations=["siem"],
            ),
            FilterConfig(name="default", destinations=["central"]),
        ]
        engine = FilterEngine(filters)

        # Auth + Critical (facility=4, severity=2)
        # Should match "critical" first
        result = engine.evaluate(make_message(facility=4, severity=2))
        assert result.filter_name == "critical"

    def test_multiple_facilities(self):
        """Test filter with multiple facilities."""
        filters = [
            FilterConfig(
                name="security",
                match=FilterMatch(facility=[Facility.AUTH, Facility.AUTHPRIV]),
                destinations=["siem"],
            ),
            FilterConfig(name="default", destinations=["central"]),
        ]
        engine = FilterEngine(filters)

        # Auth (facility=4)
        result = engine.evaluate(make_message(facility=4))
        assert result.filter_name == "security"

        # Authpriv (facility=10)
        result = engine.evaluate(make_message(facility=10))
        assert result.filter_name == "security"

        # User (facility=1)
        result = engine.evaluate(make_message(facility=1))
        assert result.filter_name == "default"

    def test_combined_facility_and_severity(self):
        """Test filter with both facility and severity."""
        filters = [
            FilterConfig(
                name="auth-errors",
                match=FilterMatch(
                    facility=[Facility.AUTH],
                    severity=[Severity.ERR, Severity.CRIT],
                ),
                destinations=["alerts"],
            ),
            FilterConfig(name="default", destinations=["central"]),
        ]
        engine = FilterEngine(filters)

        # Auth + Error (facility=4, severity=3) - matches
        result = engine.evaluate(make_message(facility=4, severity=3))
        assert result.filter_name == "auth-errors"

        # Auth + Info (facility=4, severity=6) - no match
        result = engine.evaluate(make_message(facility=4, severity=6))
        assert result.filter_name == "default"

        # User + Error (facility=1, severity=3) - no match
        result = engine.evaluate(make_message(facility=1, severity=3))
        assert result.filter_name == "default"

    def test_hostname_pattern(self):
        """Test filter with hostname pattern."""
        filters = [
            FilterConfig(
                name="prod-servers",
                match=FilterMatch(hostname_pattern=r"^prod-"),
                destinations=["production"],
            ),
            FilterConfig(name="default", destinations=["central"]),
        ]
        engine = FilterEngine(filters)

        result = engine.evaluate(make_message(hostname="prod-web-01"))
        assert result.filter_name == "prod-servers"

        result = engine.evaluate(make_message(hostname="dev-web-01"))
        assert result.filter_name == "default"

    def test_message_pattern(self):
        """Test filter with message pattern."""
        filters = [
            FilterConfig(
                name="auth-failures",
                match=FilterMatch(message_pattern=r"authentication failure|failed password"),
                destinations=["security"],
            ),
            FilterConfig(name="default", destinations=["central"]),
        ]
        engine = FilterEngine(filters)

        result = engine.evaluate(make_message(message="authentication failure for user admin"))
        assert result.filter_name == "auth-failures"

        result = engine.evaluate(make_message(message="user admin logged in successfully"))
        assert result.filter_name == "default"

    def test_filter_reload(self):
        """Test reloading filters."""
        initial_filters = [
            FilterConfig(name="default", destinations=["central"]),
        ]
        engine = FilterEngine(initial_filters)

        # Initial check
        result = engine.evaluate(make_message())
        assert result.filter_name == "default"

        # Reload with new filters
        new_filters = [
            FilterConfig(
                name="drop-all",
                action="drop",
            ),
        ]
        engine.reload(new_filters)

        # Should now use new filter
        result = engine.evaluate(make_message())
        assert result.filter_name == "drop-all"
        assert result.action == "drop"

    def test_multiple_destinations(self):
        """Test filter with multiple destinations."""
        filters = [
            FilterConfig(
                name="critical",
                match=FilterMatch(severity=[Severity.CRIT, Severity.ALERT, Severity.EMERG]),
                destinations=["siem", "pagerduty", "archive"],
            ),
        ]
        engine = FilterEngine(filters)

        result = engine.evaluate(make_message(severity=2))
        assert result.destinations == ["siem", "pagerduty", "archive"]
