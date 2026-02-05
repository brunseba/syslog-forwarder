"""Tests for message transformer."""

from datetime import datetime

import pytest

from syslog_fwd.config import MaskConfig, ReplaceConfig, TransformConfig
from syslog_fwd.parser import SyslogMessage
from syslog_fwd.transformer import MessageTransformer


def make_message(
    facility: int = 1,
    severity: int = 6,
    hostname: str | None = "testhost",
    app_name: str | None = "myapp",
    proc_id: str | None = "1234",
    msg_id: str | None = "ID47",
    structured_data: str | None = "[meta key=value]",
    message: str = "Test message",
) -> SyslogMessage:
    """Create a test syslog message."""
    return SyslogMessage(
        facility=facility,
        severity=severity,
        timestamp=datetime.now(),
        hostname=hostname,
        app_name=app_name,
        proc_id=proc_id,
        msg_id=msg_id,
        structured_data=structured_data,
        message=message,
        raw=b"",
        format="rfc5424",
    )


class TestMessageTransformer:
    """Tests for MessageTransformer class."""

    def test_no_transforms(self):
        """Test that no transforms returns original message."""
        transformer = MessageTransformer([])
        msg = make_message()
        result = transformer.transform(msg)
        assert result is msg

    def test_remove_single_field(self):
        """Test removing a single field."""
        transforms = [
            TransformConfig(name="remove-pid", remove_fields=["proc_id"]),
        ]
        transformer = MessageTransformer(transforms)

        msg = make_message(proc_id="1234")
        result = transformer.transform(msg)

        assert result.proc_id is None
        assert result.hostname == "testhost"  # Other fields unchanged

    def test_remove_multiple_fields(self):
        """Test removing multiple fields."""
        transforms = [
            TransformConfig(
                name="cleanup",
                remove_fields=["proc_id", "msg_id", "structured_data"],
            ),
        ]
        transformer = MessageTransformer(transforms)

        msg = make_message()
        result = transformer.transform(msg)

        assert result.proc_id is None
        assert result.msg_id is None
        assert result.structured_data is None
        assert result.hostname == "testhost"
        assert result.app_name == "myapp"

    def test_set_field_value(self):
        """Test setting a field to a specific value."""
        transforms = [
            TransformConfig(
                name="set-hostname",
                set_fields={"hostname": "new-hostname"},
            ),
        ]
        transformer = MessageTransformer(transforms)

        msg = make_message(hostname="old-hostname")
        result = transformer.transform(msg)

        assert result.hostname == "new-hostname"

    def test_set_multiple_fields(self):
        """Test setting multiple fields."""
        transforms = [
            TransformConfig(
                name="rewrite",
                set_fields={
                    "hostname": "forwarded",
                    "app_name": "syslog-fwd",
                },
            ),
        ]
        transformer = MessageTransformer(transforms)

        msg = make_message()
        result = transformer.transform(msg)

        assert result.hostname == "forwarded"
        assert result.app_name == "syslog-fwd"

    def test_message_replace(self):
        """Test regex replacement in message content."""
        transforms = [
            TransformConfig(
                name="replace-error",
                message_replace=ReplaceConfig(
                    pattern=r"error",
                    replacement="ERROR",
                ),
            ),
        ]
        transformer = MessageTransformer(transforms)

        msg = make_message(message="This is an error message with error details")
        result = transformer.transform(msg)

        assert result.message == "This is an ERROR message with ERROR details"

    def test_message_replace_with_groups(self):
        """Test regex replacement with capture groups."""
        transforms = [
            TransformConfig(
                name="wrap-numbers",
                message_replace=ReplaceConfig(
                    pattern=r"(\d+)",
                    replacement=r"[\1]",
                ),
            ),
        ]
        transformer = MessageTransformer(transforms)

        msg = make_message(message="User 123 logged in at port 8080")
        result = transformer.transform(msg)

        assert result.message == "User [123] logged in at port [8080]"

    def test_mask_ip_addresses(self):
        """Test masking IP addresses."""
        transforms = [
            TransformConfig(
                name="anonymize-ip",
                mask_patterns=[
                    MaskConfig(
                        pattern=r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
                        replacement="x.x.x.x",
                    ),
                ],
            ),
        ]
        transformer = MessageTransformer(transforms)

        msg = make_message(message="Connection from 192.168.1.100 to 10.0.0.1")
        result = transformer.transform(msg)

        assert result.message == "Connection from x.x.x.x to x.x.x.x"

    def test_mask_email_addresses(self):
        """Test masking email addresses."""
        transforms = [
            TransformConfig(
                name="mask-email",
                mask_patterns=[
                    MaskConfig(
                        pattern=r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
                        replacement="***@***.***",
                    ),
                ],
            ),
        ]
        transformer = MessageTransformer(transforms)

        msg = make_message(message="User user@example.com sent email to admin@company.org")
        result = transformer.transform(msg)

        assert result.message == "User ***@***.*** sent email to ***@***.***"

    def test_mask_passwords(self):
        """Test masking passwords and secrets."""
        transforms = [
            TransformConfig(
                name="mask-secrets",
                mask_patterns=[
                    MaskConfig(
                        pattern=r"(password|secret|token)=([^\s]+)",
                        replacement=r"\1=***REDACTED***",
                    ),
                ],
            ),
        ]
        transformer = MessageTransformer(transforms)

        msg = make_message(message="Login with password=mysecret123 and token=abc123")
        result = transformer.transform(msg)

        assert "mysecret123" not in result.message
        assert "abc123" not in result.message
        assert "password=***REDACTED***" in result.message
        assert "token=***REDACTED***" in result.message

    def test_message_prefix(self):
        """Test prepending to message."""
        transforms = [
            TransformConfig(
                name="add-prefix",
                message_prefix="[FORWARDED] ",
            ),
        ]
        transformer = MessageTransformer(transforms)

        msg = make_message(message="Original message")
        result = transformer.transform(msg)

        assert result.message == "[FORWARDED] Original message"

    def test_message_suffix(self):
        """Test appending to message."""
        transforms = [
            TransformConfig(
                name="add-suffix",
                message_suffix=" [processed]",
            ),
        ]
        transformer = MessageTransformer(transforms)

        msg = make_message(message="Original message")
        result = transformer.transform(msg)

        assert result.message == "Original message [processed]"

    def test_combined_transforms(self):
        """Test multiple operations in a single transform."""
        transforms = [
            TransformConfig(
                name="full-cleanup",
                remove_fields=["proc_id", "structured_data"],
                set_fields={"hostname": "proxy"},
                message_prefix="[FWD] ",
                mask_patterns=[
                    MaskConfig(pattern=r"\d+\.\d+\.\d+\.\d+", replacement="x.x.x.x"),
                ],
            ),
        ]
        transformer = MessageTransformer(transforms)

        msg = make_message(
            hostname="original",
            proc_id="123",
            structured_data="[data]",
            message="Request from 192.168.1.1",
        )
        result = transformer.transform(msg)

        assert result.hostname == "proxy"
        assert result.proc_id is None
        assert result.structured_data is None
        assert result.message == "[FWD] Request from x.x.x.x"

    def test_match_pattern_applies_selectively(self):
        """Test that match_pattern limits which messages are transformed."""
        transforms = [
            TransformConfig(
                name="error-only",
                match_pattern=r"error|ERROR",
                message_prefix="[!] ",
            ),
        ]
        transformer = MessageTransformer(transforms)

        # Should be transformed
        msg1 = make_message(message="An error occurred")
        result1 = transformer.transform(msg1)
        assert result1.message == "[!] An error occurred"

        # Should NOT be transformed
        msg2 = make_message(message="Everything is fine")
        result2 = transformer.transform(msg2)
        assert result2.message == "Everything is fine"

    def test_multiple_transforms_in_sequence(self):
        """Test applying multiple transforms in sequence."""
        transforms = [
            TransformConfig(name="step1", message_prefix="[1]"),
            TransformConfig(name="step2", message_prefix="[2]"),
            TransformConfig(name="step3", message_prefix="[3]"),
        ]
        transformer = MessageTransformer(transforms)

        msg = make_message(message="msg")
        result = transformer.transform(msg)

        assert result.message == "[3][2][1]msg"

    def test_transform_by_name(self):
        """Test applying specific transforms by name."""
        transforms = [
            TransformConfig(name="prefix-a", message_prefix="[A]"),
            TransformConfig(name="prefix-b", message_prefix="[B]"),
            TransformConfig(name="prefix-c", message_prefix="[C]"),
        ]
        transformer = MessageTransformer(transforms)

        msg = make_message(message="msg")

        # Apply only specific transforms
        result = transformer.transform(msg, ["prefix-b"])
        assert result.message == "[B]msg"

        # Apply multiple specific transforms
        result = transformer.transform(msg, ["prefix-a", "prefix-c"])
        assert result.message == "[C][A]msg"

    def test_transform_reload(self):
        """Test reloading transformer configuration."""
        initial_transforms = [
            TransformConfig(name="old", message_prefix="[OLD]"),
        ]
        transformer = MessageTransformer(initial_transforms)

        msg = make_message(message="test")
        result = transformer.transform(msg)
        assert result.message == "[OLD]test"

        # Reload with new transforms
        new_transforms = [
            TransformConfig(name="new", message_prefix="[NEW]"),
        ]
        transformer.reload(new_transforms)

        result = transformer.transform(msg)
        assert result.message == "[NEW]test"

    def test_original_message_unchanged(self):
        """Test that original message is not mutated."""
        transforms = [
            TransformConfig(name="modify", set_fields={"hostname": "changed"}),
        ]
        transformer = MessageTransformer(transforms)

        msg = make_message(hostname="original")
        result = transformer.transform(msg)

        assert msg.hostname == "original"  # Original unchanged
        assert result.hostname == "changed"  # New message changed
