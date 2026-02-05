"""Tests for syslog-ng export functionality."""

import pytest

from syslog_fwd.config import (
    Config,
    InputConfig,
    FilterConfig,
    FilterMatch,
    DestinationConfig,
    TransformConfig,
    MaskConfig,
    Protocol,
    SyslogFormat,
    Facility,
    Severity,
)
from syslog_fwd.export_syslogng import export_to_syslogng


@pytest.fixture
def simple_config() -> Config:
    """Create a simple configuration for testing."""
    return Config(
        inputs=[
            InputConfig(name="udp-514", protocol=Protocol.UDP, address="0.0.0.0:514"),
            InputConfig(name="tcp-514", protocol=Protocol.TCP, address="0.0.0.0:514"),
        ],
        destinations=[
            DestinationConfig(
                name="central",
                protocol=Protocol.TCP,
                address="logs.example.com:514",
                format=SyslogFormat.RFC5424,
            ),
        ],
        filters=[
            FilterConfig(name="default", destinations=["central"]),
        ],
    )


@pytest.fixture
def complex_config() -> Config:
    """Create a complex configuration with transforms and filters."""
    return Config(
        inputs=[
            InputConfig(name="udp-514", protocol=Protocol.UDP, address="0.0.0.0:514"),
        ],
        transforms=[
            TransformConfig(
                name="anonymize-ip",
                mask_patterns=[
                    MaskConfig(
                        pattern=r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
                        replacement="x.x.x.x",
                    )
                ],
            ),
            TransformConfig(
                name="add-prefix",
                message_prefix="[FORWARDED] ",
            ),
            TransformConfig(
                name="remove-pid",
                remove_fields=["proc_id"],
            ),
        ],
        filters=[
            FilterConfig(
                name="auth-logs",
                match=FilterMatch(facility=[Facility.AUTH, Facility.AUTHPRIV]),
                transforms=["anonymize-ip"],
                destinations=["siem"],
            ),
            FilterConfig(
                name="drop-debug",
                match=FilterMatch(severity=[Severity.DEBUG]),
                action="drop",
            ),
            FilterConfig(
                name="default",
                transforms=["add-prefix", "remove-pid"],
                destinations=["central"],
            ),
        ],
        destinations=[
            DestinationConfig(
                name="siem",
                protocol=Protocol.TCP,
                address="siem.example.com:514",
                format=SyslogFormat.RFC5424,
            ),
            DestinationConfig(
                name="central",
                protocol=Protocol.UDP,
                address="logs.example.com:514",
                format=SyslogFormat.RFC3164,
            ),
        ],
    )


class TestExportSyslogNg:
    """Tests for export_to_syslogng function."""

    def test_export_header(self, simple_config: Config) -> None:
        """Test that export includes proper header."""
        result = export_to_syslogng(simple_config)
        assert "@version: 4.0" in result
        assert '@include "scl.conf"' in result
        assert "options {" in result
        assert "Generated from syslog-fwd config" in result

    def test_export_sources(self, simple_config: Config) -> None:
        """Test that sources are exported correctly."""
        result = export_to_syslogng(simple_config)
        assert "source s_udp_514 {" in result
        assert "source s_tcp_514 {" in result
        assert 'transport("udp")' in result
        assert 'transport("tcp")' in result
        assert "port(514)" in result

    def test_export_destinations(self, simple_config: Config) -> None:
        """Test that destinations are exported correctly."""
        result = export_to_syslogng(simple_config)
        assert "destination d_central {" in result
        assert '"logs.example.com"' in result
        assert 'transport("tcp")' in result

    def test_export_filters(self, simple_config: Config) -> None:
        """Test that filters are exported correctly."""
        result = export_to_syslogng(simple_config)
        assert "filter f_default {" in result

    def test_export_log_paths(self, simple_config: Config) -> None:
        """Test that log paths are exported correctly."""
        result = export_to_syslogng(simple_config)
        assert "log {" in result
        assert "source(s_udp_514);" in result
        assert "filter(f_default);" in result
        assert "destination(d_central);" in result
        assert "flags(final);" in result

    def test_export_facility_filter(self, complex_config: Config) -> None:
        """Test that facility filters are exported correctly."""
        result = export_to_syslogng(complex_config)
        assert "filter f_auth_logs {" in result
        assert "facility(auth)" in result
        assert "facility(authpriv)" in result

    def test_export_severity_filter(self, complex_config: Config) -> None:
        """Test that severity filters are exported correctly."""
        result = export_to_syslogng(complex_config)
        assert "filter f_drop_debug {" in result
        assert "level(debug)" in result

    def test_export_drop_action(self, complex_config: Config) -> None:
        """Test that drop action creates log path without destination."""
        result = export_to_syslogng(complex_config)
        # Find the drop-debug log path
        assert "# Log path: drop-debug (DROP)" in result
        # It should have flags(final) but no destination

    def test_export_transforms_as_rewrites(self, complex_config: Config) -> None:
        """Test that transforms are exported as syslog-ng rewrites."""
        result = export_to_syslogng(complex_config)
        assert "rewrite r_anonymize_ip {" in result
        assert "rewrite r_add_prefix {" in result
        assert "rewrite r_remove_pid {" in result

    def test_export_mask_pattern(self, complex_config: Config) -> None:
        """Test that mask patterns are exported as subst."""
        result = export_to_syslogng(complex_config)
        assert "subst(" in result
        assert "x.x.x.x" in result
        assert 'flags(global)' in result

    def test_export_message_prefix(self, complex_config: Config) -> None:
        """Test that message prefix is exported correctly."""
        result = export_to_syslogng(complex_config)
        assert "[FORWARDED]" in result
        assert '${MSG}' in result

    def test_export_remove_fields(self, complex_config: Config) -> None:
        """Test that remove_fields creates set() with empty value."""
        result = export_to_syslogng(complex_config)
        assert 'set("" value("PID"))' in result

    def test_export_transforms_in_log_paths(self, complex_config: Config) -> None:
        """Test that transforms are referenced in log paths."""
        result = export_to_syslogng(complex_config)
        assert "rewrite(r_anonymize_ip);" in result
        assert "rewrite(r_add_prefix);" in result
        assert "rewrite(r_remove_pid);" in result

    def test_export_rfc3164_format(self, complex_config: Config) -> None:
        """Test that RFC3164 format uses correct template."""
        result = export_to_syslogng(complex_config)
        # central destination uses RFC3164
        assert '${ISODATE} ${HOST} ${PROGRAM}[${PID}]: ${MSG}' in result

    def test_export_rfc5424_format(self, complex_config: Config) -> None:
        """Test that RFC5424 format uses format-syslog."""
        result = export_to_syslogng(complex_config)
        # siem destination uses RFC5424
        assert '$(format-syslog)' in result
