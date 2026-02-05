"""Message transformation for syslog messages."""

import re
from dataclasses import replace

import structlog

from .config import MaskConfig, TransformConfig
from .parser import SyslogMessage

logger = structlog.get_logger()


class MessageTransformer:
    """Transform syslog messages by modifying or removing fields."""

    def __init__(self, transforms: list[TransformConfig]) -> None:
        """Initialize transformer with a list of transformations.

        Args:
            transforms: List of transformation configurations.
        """
        self.transforms = transforms
        self._transforms_by_name: dict[str, TransformConfig] = {t.name: t for t in transforms}
        self._compiled_patterns: dict[str, re.Pattern] = {}
        self._compile_patterns()
        self.log = logger.bind(component="transformer")

    def _compile_patterns(self) -> None:
        """Pre-compile regex patterns for performance."""
        for t in self.transforms:
            if t.match_pattern:
                self._compiled_patterns[t.name] = re.compile(t.match_pattern)
            if t.message_replace and t.message_replace.pattern:
                key = f"{t.name}_replace"
                self._compiled_patterns[key] = re.compile(t.message_replace.pattern)
            if t.mask_patterns:
                for i, mask in enumerate(t.mask_patterns):
                    key = f"{t.name}_mask_{i}"
                    self._compiled_patterns[key] = re.compile(mask.pattern)

    def transform(self, message: SyslogMessage, transform_names: list[str] | None = None) -> SyslogMessage:
        """Apply transformations to a message.

        Args:
            message: Original syslog message.
            transform_names: Specific transforms to apply. If None, applies all.

        Returns:
            Transformed message (may be the same object if no transforms applied).
        """
        result = message

        if transform_names:
            # Apply only specified transforms in order
            for name in transform_names:
                t = self._transforms_by_name.get(name)
                if t and self._should_apply(t, result):
                    result = self._apply_transform(t, result)
        else:
            # Apply all transforms
            for t in self.transforms:
                if self._should_apply(t, result):
                    result = self._apply_transform(t, result)

        return result

    def _should_apply(self, transform: TransformConfig, message: SyslogMessage) -> bool:
        """Check if a transformation should be applied to a message."""
        # If no match_pattern, apply to all messages
        if not transform.match_pattern:
            return True

        pattern = self._compiled_patterns.get(transform.name)
        if pattern:
            return bool(pattern.search(message.message))
        return False

    def _apply_transform(
        self, transform: TransformConfig, message: SyslogMessage
    ) -> SyslogMessage:
        """Apply a single transformation to a message."""
        changes: dict = {}

        # Remove fields
        if transform.remove_fields:
            for field in transform.remove_fields:
                if field == "hostname":
                    changes["hostname"] = None
                elif field == "app_name":
                    changes["app_name"] = None
                elif field == "proc_id":
                    changes["proc_id"] = None
                elif field == "msg_id":
                    changes["msg_id"] = None
                elif field == "structured_data":
                    changes["structured_data"] = None

        # Set fields to specific values
        if transform.set_fields:
            for field, value in transform.set_fields.items():
                if field in ("hostname", "app_name", "proc_id", "msg_id", "structured_data"):
                    changes[field] = value
                elif field == "facility":
                    changes["facility"] = int(value)
                elif field == "severity":
                    changes["severity"] = int(value)

        # Replace in message content
        if transform.message_replace:
            pattern = self._compiled_patterns.get(f"{transform.name}_replace")
            if pattern:
                new_message = pattern.sub(
                    transform.message_replace.replacement,
                    message.message,
                )
                changes["message"] = new_message

        # Mask sensitive data
        if transform.mask_patterns:
            new_message = changes.get("message", message.message)
            for i, mask in enumerate(transform.mask_patterns):
                pattern = self._compiled_patterns.get(f"{transform.name}_mask_{i}")
                if pattern:
                    new_message = pattern.sub(mask.replacement, new_message)
            changes["message"] = new_message

        # Prepend/append to message
        if transform.message_prefix:
            msg = changes.get("message", message.message)
            changes["message"] = transform.message_prefix + msg

        if transform.message_suffix:
            msg = changes.get("message", message.message)
            changes["message"] = msg + transform.message_suffix

        # Apply changes using dataclass replace
        if changes:
            return replace(message, **changes)

        return message

    def reload(self, transforms: list[TransformConfig]) -> None:
        """Reload transformer with new configurations."""
        self.transforms = transforms
        self._transforms_by_name = {t.name: t for t in transforms}
        self._compiled_patterns.clear()
        self._compile_patterns()
        self.log.info("Transforms reloaded", count=len(transforms))


# Common transformation presets
PRESET_TRANSFORMS: dict[str, TransformConfig] = {
    "remove-pid": TransformConfig(
        name="remove-pid",
        remove_fields=["proc_id"],
    ),
    "remove-structured-data": TransformConfig(
        name="remove-structured-data",
        remove_fields=["structured_data"],
    ),
    "anonymize-ip": TransformConfig(
        name="anonymize-ip",
        mask_patterns=[
            MaskConfig(
                pattern=r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
                replacement="x.x.x.x",
            ),
        ],
    ),
    "mask-email": TransformConfig(
        name="mask-email",
        mask_patterns=[
            MaskConfig(
                pattern=r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
                replacement="***@***.***",
            ),
        ],
    ),
    "mask-password": TransformConfig(
        name="mask-password",
        mask_patterns=[
            MaskConfig(
                pattern=r"(password|passwd|pwd|secret|token|api_key|apikey)[\s]*[=:][\s]*['\"]?([^'\"\s]+)['\"]?",
                replacement=r"\1=***REDACTED***",
            ),
        ],
    ),
}
