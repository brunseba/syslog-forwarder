"""Filter engine for syslog message routing."""

import re
import time
from dataclasses import dataclass

import structlog

from .config import FACILITY_MAP, SEVERITY_MAP, FilterConfig
from .metrics import MESSAGES_DROPPED, PROCESSING_LATENCY
from .parser import SyslogMessage

logger = structlog.get_logger()


@dataclass
class FilterResult:
    """Result of filter evaluation."""

    matched: bool
    filter_name: str | None
    action: str  # "forward" or "drop"
    destinations: list[str]


class FilterEngine:
    """Engine for evaluating filter rules against syslog messages."""

    def __init__(self, filters: list[FilterConfig]) -> None:
        """Initialize filter engine.

        Args:
            filters: List of filter configurations.
        """
        self.filters = filters
        self._compiled_patterns: dict[str, tuple[re.Pattern | None, re.Pattern | None]] = {}
        self._compile_patterns()
        self.log = logger.bind(component="filter_engine")

    def _compile_patterns(self) -> None:
        """Pre-compile regex patterns for performance."""
        for f in self.filters:
            hostname_pattern = None
            message_pattern = None
            if f.match:
                if f.match.hostname_pattern:
                    hostname_pattern = re.compile(f.match.hostname_pattern)
                if f.match.message_pattern:
                    message_pattern = re.compile(f.match.message_pattern)
            self._compiled_patterns[f.name] = (hostname_pattern, message_pattern)

    def evaluate(self, message: SyslogMessage) -> FilterResult:
        """Evaluate a message against all filters.

        Uses first-match-wins semantics.

        Args:
            message: Parsed syslog message.

        Returns:
            FilterResult with match information.
        """
        start_time = time.perf_counter()

        for f in self.filters:
            if self._matches(f, message):
                elapsed = time.perf_counter() - start_time
                PROCESSING_LATENCY.labels(filter=f.name).observe(elapsed)

                if f.action == "drop":
                    MESSAGES_DROPPED.labels(reason=f"filter:{f.name}").inc()
                    return FilterResult(
                        matched=True,
                        filter_name=f.name,
                        action="drop",
                        destinations=[],
                    )

                return FilterResult(
                    matched=True,
                    filter_name=f.name,
                    action="forward",
                    destinations=f.destinations or [],
                )

        # No filter matched - drop by default
        elapsed = time.perf_counter() - start_time
        PROCESSING_LATENCY.labels(filter="none").observe(elapsed)
        MESSAGES_DROPPED.labels(reason="no_match").inc()

        return FilterResult(
            matched=False,
            filter_name=None,
            action="drop",
            destinations=[],
        )

    def _matches(self, filter_config: FilterConfig, message: SyslogMessage) -> bool:
        """Check if a message matches a filter's criteria.

        Args:
            filter_config: Filter configuration.
            message: Parsed syslog message.

        Returns:
            True if the message matches all criteria.
        """
        # No match criteria = match everything (catch-all filter)
        if filter_config.match is None:
            return True

        match = filter_config.match

        # Check facility
        if match.facility:
            facility_values = {FACILITY_MAP[f.value] for f in match.facility}
            if message.facility not in facility_values:
                return False

        # Check severity
        if match.severity:
            severity_values = {SEVERITY_MAP[s.value] for s in match.severity}
            if message.severity not in severity_values:
                return False

        # Check hostname pattern
        hostname_pattern, message_pattern = self._compiled_patterns.get(
            filter_config.name, (None, None)
        )

        if hostname_pattern and message.hostname:
            if not hostname_pattern.search(message.hostname):
                return False
        elif hostname_pattern and not message.hostname:
            # Filter requires hostname but message has none
            return False

        # Check message pattern
        if message_pattern:
            if not message_pattern.search(message.message):
                return False

        return True

    def reload(self, filters: list[FilterConfig]) -> None:
        """Reload filter configuration.

        Args:
            filters: New filter configurations.
        """
        self.filters = filters
        self._compiled_patterns.clear()
        self._compile_patterns()
        self.log.info("Filters reloaded", count=len(filters))
