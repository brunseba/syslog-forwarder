"""Syslog input listeners (UDP and TCP)."""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from typing import Any

import structlog

from .config import InputConfig, Protocol
from .metrics import ACTIVE_CONNECTIONS, MESSAGES_PARSE_ERRORS, MESSAGES_RECEIVED
from .parser import SyslogMessage, SyslogParser

logger = structlog.get_logger()

# Type alias for message handler callback
MessageHandler = Callable[[SyslogMessage], Coroutine[Any, Any, None]]


class BaseInput(ABC):
    """Base class for syslog input listeners."""

    def __init__(self, config: InputConfig, handler: MessageHandler) -> None:
        """Initialize input listener.

        Args:
            config: Input configuration.
            handler: Async callback for received messages.
        """
        self.config = config
        self.handler = handler
        self.log = logger.bind(input=config.name, protocol=config.protocol.value)

    @abstractmethod
    async def start(self) -> None:
        """Start the input listener."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the input listener."""


class UDPInput(BaseInput):
    """UDP syslog input listener."""

    def __init__(self, config: InputConfig, handler: MessageHandler) -> None:
        super().__init__(config, handler)
        self._transport: asyncio.DatagramTransport | None = None
        self._protocol: "UDPProtocol | None" = None

    async def start(self) -> None:
        """Start UDP listener."""
        loop = asyncio.get_running_loop()
        self._transport, self._protocol = await loop.create_datagram_endpoint(
            lambda: UDPProtocol(self.config.name, self.handler),
            local_addr=(self.config.host, self.config.port),
        )
        self.log.info("UDP listener started", address=self.config.address)

    async def stop(self) -> None:
        """Stop UDP listener."""
        if self._transport:
            self._transport.close()
            self._transport = None
            self._protocol = None
        self.log.info("UDP listener stopped")


class UDPProtocol(asyncio.DatagramProtocol):
    """asyncio protocol for UDP syslog."""

    def __init__(self, input_name: str, handler: MessageHandler) -> None:
        self.input_name = input_name
        self.handler = handler
        self.log = logger.bind(input=input_name)

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        """Handle received UDP datagram."""
        try:
            message = SyslogParser.parse(data)
            MESSAGES_RECEIVED.labels(
                protocol="udp",
                facility=message.facility_name,
                severity=message.severity_name,
            ).inc()
            # Schedule the async handler
            asyncio.create_task(self.handler(message))
        except ValueError as e:
            MESSAGES_PARSE_ERRORS.labels(protocol="udp").inc()
            self.log.warning("Failed to parse message", error=str(e), addr=addr)

    def error_received(self, exc: Exception) -> None:
        """Handle UDP error."""
        self.log.error("UDP error", error=str(exc))


class TCPInput(BaseInput):
    """TCP syslog input listener."""

    def __init__(self, config: InputConfig, handler: MessageHandler) -> None:
        super().__init__(config, handler)
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        """Start TCP listener."""
        self._server = await asyncio.start_server(
            self._handle_client,
            self.config.host,
            self.config.port,
        )
        self.log.info("TCP listener started", address=self.config.address)

    async def stop(self) -> None:
        """Stop TCP listener."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self.log.info("TCP listener stopped")

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle a TCP client connection."""
        addr = writer.get_extra_info("peername")
        self.log.debug("Client connected", addr=addr)
        ACTIVE_CONNECTIONS.labels(input=self.config.name).inc()

        try:
            buffer = b""
            while True:
                # Read data from client
                data = await reader.read(8192)
                if not data:
                    break

                buffer += data

                # Process complete messages (newline-delimited or octet-counting)
                while buffer:
                    # Try octet-counting first (RFC 6587)
                    message_data, buffer = self._extract_message(buffer)
                    if message_data is None:
                        break

                    try:
                        message = SyslogParser.parse(message_data)
                        MESSAGES_RECEIVED.labels(
                            protocol="tcp",
                            facility=message.facility_name,
                            severity=message.severity_name,
                        ).inc()
                        await self.handler(message)
                    except ValueError as e:
                        MESSAGES_PARSE_ERRORS.labels(protocol="tcp").inc()
                        self.log.warning("Failed to parse message", error=str(e), addr=addr)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.log.error("Error handling client", error=str(e), addr=addr)
        finally:
            ACTIVE_CONNECTIONS.labels(input=self.config.name).dec()
            writer.close()
            await writer.wait_closed()
            self.log.debug("Client disconnected", addr=addr)

    def _extract_message(self, buffer: bytes) -> tuple[bytes | None, bytes]:
        """Extract a complete message from the buffer.

        Supports both newline framing and octet-counting (RFC 6587).

        Returns:
            Tuple of (message_data, remaining_buffer).
            message_data is None if no complete message is available.
        """
        if not buffer:
            return None, buffer

        # Check for octet-counting: "LEN SP MSG"
        # e.g., "123 <...message...>"
        if buffer[0:1].isdigit():
            # Find the space after the length
            space_idx = buffer.find(b" ")
            if space_idx > 0 and space_idx < 10:  # Reasonable length field
                try:
                    msg_len = int(buffer[:space_idx])
                    msg_start = space_idx + 1
                    msg_end = msg_start + msg_len
                    if len(buffer) >= msg_end:
                        return buffer[msg_start:msg_end], buffer[msg_end:]
                except ValueError:
                    pass

        # Fall back to newline framing
        newline_idx = buffer.find(b"\n")
        if newline_idx >= 0:
            return buffer[:newline_idx], buffer[newline_idx + 1 :]

        # Check for CR+LF
        crlf_idx = buffer.find(b"\r\n")
        if crlf_idx >= 0:
            return buffer[:crlf_idx], buffer[crlf_idx + 2 :]

        # No complete message yet
        return None, buffer


def create_input(config: InputConfig, handler: MessageHandler) -> BaseInput:
    """Create an input listener based on configuration.

    Args:
        config: Input configuration.
        handler: Async callback for received messages.

    Returns:
        Configured input listener.

    Raises:
        ValueError: If the protocol is not supported.
    """
    if config.protocol == Protocol.UDP:
        return UDPInput(config, handler)
    elif config.protocol == Protocol.TCP:
        return TCPInput(config, handler)
    elif config.protocol == Protocol.TLS:
        raise ValueError("TLS input not yet implemented")
    else:
        raise ValueError(f"Unknown protocol: {config.protocol}")
