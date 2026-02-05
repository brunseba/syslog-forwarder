"""Tests for configuration models."""

import os
import tempfile
from pathlib import Path

import pytest

from syslog_fwd.config import (
    Config,
    DestinationConfig,
    FilterConfig,
    FilterMatch,
    InputConfig,
    Protocol,
    Facility,
    Severity,
    SyslogFormat,
    load_config,
)


class TestInputConfig:
    """Tests for InputConfig model."""

    def test_valid_input(self):
        """Test valid input configuration."""
        config = InputConfig(name="test", protocol=Protocol.UDP, address="0.0.0.0:514")
        assert config.name == "test"
        assert config.host == "0.0.0.0"
        assert config.port == 514

    def test_invalid_address_no_port(self):
        """Test that address without port raises error."""
        with pytest.raises(ValueError, match="host:port"):
            InputConfig(name="test", address="localhost")

    def test_invalid_port_range(self):
        """Test that invalid port range raises error."""
        with pytest.raises(ValueError, match="Port must be"):
            InputConfig(name="test", address="localhost:99999")


class TestFilterConfig:
    """Tests for FilterConfig model."""

    def test_forward_filter_requires_destinations(self):
        """Test that forward filter requires destinations."""
        with pytest.raises(ValueError, match="must specify destinations"):
            FilterConfig(name="test", action="forward")

    def test_drop_filter_no_destinations(self):
        """Test that drop filter should not have destinations."""
        with pytest.raises(ValueError, match="should not have destinations"):
            FilterConfig(name="test", action="drop", destinations=["dest"])

    def test_valid_forward_filter(self):
        """Test valid forward filter."""
        config = FilterConfig(name="test", action="forward", destinations=["dest1"])
        assert config.action == "forward"
        assert config.destinations == ["dest1"]

    def test_valid_drop_filter(self):
        """Test valid drop filter."""
        config = FilterConfig(name="test", action="drop")
        assert config.action == "drop"
        assert config.destinations is None

    def test_catch_all_filter(self):
        """Test catch-all filter with no match criteria."""
        config = FilterConfig(name="default", destinations=["central"])
        assert config.match is None


class TestFilterMatch:
    """Tests for FilterMatch model."""

    def test_valid_regex_pattern(self):
        """Test valid regex pattern."""
        match = FilterMatch(message_pattern=r"error|warning")
        assert match.message_pattern == "error|warning"

    def test_invalid_regex_pattern(self):
        """Test invalid regex pattern raises error."""
        with pytest.raises(ValueError, match="Invalid regex"):
            FilterMatch(message_pattern=r"[invalid")

    def test_facility_filter(self):
        """Test facility filter."""
        match = FilterMatch(facility=[Facility.AUTH, Facility.AUTHPRIV])
        assert len(match.facility) == 2


class TestDestinationConfig:
    """Tests for DestinationConfig model."""

    def test_valid_destination(self):
        """Test valid destination configuration."""
        config = DestinationConfig(
            name="siem",
            protocol=Protocol.TCP,
            address="siem.example.com:514",
            format=SyslogFormat.RFC5424,
        )
        assert config.host == "siem.example.com"
        assert config.port == 514

    def test_default_retry_config(self):
        """Test default retry configuration."""
        config = DestinationConfig(name="test", address="localhost:514")
        assert config.retry.max_attempts == 3
        assert config.retry.backoff_seconds == 1.0


class TestConfig:
    """Tests for root Config model."""

    def test_validate_destination_references(self):
        """Test that invalid destination references are caught."""
        with pytest.raises(ValueError, match="unknown destination"):
            Config(
                filters=[
                    FilterConfig(name="test", destinations=["nonexistent"])
                ],
                destinations=[],
            )

    def test_valid_config(self):
        """Test valid complete configuration."""
        config = Config(
            inputs=[
                InputConfig(name="udp", address="0.0.0.0:514"),
            ],
            filters=[
                FilterConfig(name="default", destinations=["central"]),
            ],
            destinations=[
                DestinationConfig(name="central", address="logs.example.com:514"),
            ],
        )
        assert len(config.inputs) == 1
        assert len(config.filters) == 1
        assert len(config.destinations) == 1


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_valid_config(self):
        """Test loading a valid configuration file."""
        config_content = """
version: "1"
inputs:
  - name: udp-514
    protocol: udp
    address: "0.0.0.0:514"
filters:
  - name: default
    destinations: [central]
destinations:
  - name: central
    protocol: udp
    address: "logs.example.com:514"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            f.flush()

            try:
                config = load_config(f.name)
                assert len(config.inputs) == 1
                assert config.inputs[0].name == "udp-514"
            finally:
                os.unlink(f.name)

    def test_load_nonexistent_file(self):
        """Test that loading nonexistent file raises error."""
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")

    def test_env_var_substitution(self):
        """Test environment variable substitution."""
        os.environ["TEST_HOST"] = "siem.test.com"
        os.environ["TEST_PORT"] = "6514"

        config_content = """
version: "1"
destinations:
  - name: test
    address: "${TEST_HOST}:${TEST_PORT}"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            f.flush()

            try:
                config = load_config(f.name)
                assert config.destinations[0].host == "siem.test.com"
                assert config.destinations[0].port == 6514
            finally:
                os.unlink(f.name)
                del os.environ["TEST_HOST"]
                del os.environ["TEST_PORT"]

    def test_env_var_with_default(self):
        """Test environment variable substitution with default."""
        # Make sure var is not set
        if "UNSET_VAR" in os.environ:
            del os.environ["UNSET_VAR"]

        config_content = """
version: "1"
destinations:
  - name: test
    address: "${UNSET_VAR:-default.example.com}:514"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            f.flush()

            try:
                config = load_config(f.name)
                assert config.destinations[0].host == "default.example.com"
            finally:
                os.unlink(f.name)

    def test_empty_config_uses_defaults(self):
        """Test that empty config uses default values."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            f.flush()

            try:
                config = load_config(f.name)
                assert config.version == "1"
                assert len(config.inputs) == 0
                assert config.service.log_level == "info"
            finally:
                os.unlink(f.name)
