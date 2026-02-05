"""Syslog output forwarders (UDP and TCP)."""

import asyncio
import socket
from abc import ABC, abstractmethod

import structlog

from .config import DestinationConfig, Protocol, SyslogFormat
from .metrics import DESTINATION_UP, MESSAGES_FORWARDED
from .parser import SyslogMessage

logger = structlog.get_logger()


class BaseOutput(ABC):
    """Base class for syslog output forwarders."""

    def __init__(self, config: DestinationConfig) -> None:
        """Initialize output forwarder.

        Args:
            config: Destination configuration.
        """
        self.config = config
        self.log = logger.bind(destination=config.name, protocol=config.protocol.value)
        self._connected = False

    @property
    def connected(self) -> bool:
        """Check if the forwarder is connected."""
        return self._connected

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to destination."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to destination."""

    @abstractmethod
    async def send(self, message: SyslogMessage) -> bool:
        """Send a message to the destination.

        Args:
            message: Parsed syslog message.

        Returns:
            True if successful, False otherwise.
        """

    def _format_message(self, message: SyslogMessage) -> bytes:
        """Format message according to destination configuration.

        Args:
            message: Parsed syslog message.

        Returns:
            Formatted message bytes.
        """
        if self.config.format == SyslogFormat.RFC5424:
            return message.to_rfc5424()
        elif self.config.format == SyslogFormat.RFC3164:
            return message.to_rfc3164()
        else:
            # AUTO - use original format
            if message.format == "rfc5424":
                return message.to_rfc5424()
            else:
                return message.to_rfc3164()

    async def send_with_retry(self, message: SyslogMessage) -> bool:
        """Send a message with retry logic.

        Args:
            message: Parsed syslog message.

        Returns:
            True if successful, False after all retries failed.
        """
        max_attempts = self.config.retry.max_attempts
        backoff = self.config.retry.backoff_seconds

        for attempt in range(max_attempts):
            try:
                if not self._connected:
                    await self.connect()

                if await self.send(message):
                    MESSAGES_FORWARDED.labels(destination=self.config.name).inc()
                    return True

            except Exception as e:
                self.log.warning(
                    "Send failed",
                    attempt=attempt + 1,
                    max_attempts=max_attempts,
                    error=str(e),
                )
                self._connected = False
                DESTINATION_UP.labels(destination=self.config.name).set(0)

                if attempt < max_attempts - 1:
                    await asyncio.sleep(backoff * (2**attempt))

        return False


class UDPOutput(BaseOutput):
    """UDP syslog output forwarder."""

    def __init__(self, config: DestinationConfig) -> None:
        super().__init__(config)
        self._socket: socket.socket | None = None

    async def connect(self) -> None:
        """Create UDP socket."""
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setblocking(False)
            self._connected = True
            DESTINATION_UP.labels(destination=self.config.name).set(1)
            self.log.info("UDP forwarder ready", address=self.config.address)
        except Exception as e:
            self._connected = False
            DESTINATION_UP.labels(destination=self.config.name).set(0)
            raise ConnectionError(f"Failed to create UDP socket: {e}") from e

    async def disconnect(self) -> None:
        """Close UDP socket."""
        if self._socket:
            self._socket.close()
            self._socket = None
        self._connected = False
        DESTINATION_UP.labels(destination=self.config.name).set(0)
        self.log.info("UDP forwarder disconnected")

    async def send(self, message: SyslogMessage) -> bool:
        """Send message via UDP."""
        if not self._socket:
            return False

        data = self._format_message(message)
        loop = asyncio.get_running_loop()

        try:
            await loop.sock_sendto(self._socket, data, (self.config.host, self.config.port))
            return True
        except Exception as e:
            self.log.error("UDP send failed", error=str(e))
            return False


class TCPOutput(BaseOutput):
    """TCP syslog output forwarder."""

    def __init__(self, config: DestinationConfig) -> None:
        super().__init__(config)
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Establish TCP connection."""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.config.host, self.config.port),
                timeout=10.0,
            )
            self._connected = True
            DESTINATION_UP.labels(destination=self.config.name).set(1)
            self.log.info("TCP forwarder connected", address=self.config.address)
        except asyncio.TimeoutError as e:
            self._connected = False
            DESTINATION_UP.labels(destination=self.config.name).set(0)
            raise ConnectionError(f"Connection timeout: {self.config.address}") from e
        except Exception as e:
            self._connected = False
            DESTINATION_UP.labels(destination=self.config.name).set(0)
            raise ConnectionError(f"Failed to connect: {e}") from e

    async def disconnect(self) -> None:
        """Close TCP connection."""
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None
        self._connected = False
        DESTINATION_UP.labels(destination=self.config.name).set(0)
        self.log.info("TCP forwarder disconnected")

    async def send(self, message: SyslogMessage) -> bool:
        """Send message via TCP with newline framing."""
        if not self._writer:
            return False

        data = self._format_message(message)
        # Add newline for framing
        data = data + b"\n"

        async with self._lock:
            try:
                self._writer.write(data)
                await asyncio.wait_for(self._writer.drain(), timeout=5.0)
                return True
            except asyncio.TimeoutError:
                self.log.error("TCP send timeout")
                self._connected = False
                return False
            except Exception as e:
                self.log.error("TCP send failed", error=str(e))
                self._connected = False
                return False


def create_output(config: DestinationConfig) -> BaseOutput:
    """Create an output forwarder based on configuration.

    Args:
        config: Destination configuration.

    Returns:
        Configured output forwarder.

    Raises:
        ValueError: If the protocol is not supported.
    """
    if config.protocol == Protocol.UDP:
        return UDPOutput(config)
    elif config.protocol == Protocol.TCP:
        return TCPOutput(config)
    elif config.protocol == Protocol.TLS:
        raise ValueError("TLS output not yet implemented")
    else:
        raise ValueError(f"Unknown protocol: {config.protocol}")
