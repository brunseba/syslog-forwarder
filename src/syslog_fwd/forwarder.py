"""Main syslog forwarder service."""

import asyncio
import signal
from http.server import HTTPServer
from threading import Thread

import structlog
from prometheus_client import MetricsHandler

from .config import Config
from .filters import FilterEngine
from .inputs import BaseInput, MessageHandler, create_input
from .outputs import BaseOutput, create_output
from .parser import SyslogMessage
from .transformer import MessageTransformer

logger = structlog.get_logger()


class SyslogForwarder:
    """Main syslog forwarder service."""

    def __init__(self, config: Config) -> None:
        """Initialize the forwarder.

        Args:
            config: Validated configuration.
        """
        self.config = config
        self.log = logger.bind(component="forwarder")

        # Initialize components
        self.transformer = MessageTransformer(config.transforms)
        self.filter_engine = FilterEngine(config.filters)
        self.inputs: list[BaseInput] = []
        self.outputs: dict[str, BaseOutput] = {}

        # Create message handler
        handler: MessageHandler = self._handle_message

        # Create inputs
        for input_config in config.inputs:
            self.inputs.append(create_input(input_config, handler))

        # Create outputs
        for dest_config in config.destinations:
            self.outputs[dest_config.name] = create_output(dest_config)

        self._running = False
        self._metrics_server: HTTPServer | None = None
        self._metrics_thread: Thread | None = None

    async def _handle_message(self, message: SyslogMessage) -> None:
        """Handle a received syslog message.

        Args:
            message: Parsed syslog message.
        """
        # Evaluate filters
        result = self.filter_engine.evaluate(message)

        if result.action == "drop":
            self.log.debug(
                "Message dropped",
                filter=result.filter_name,
                facility=message.facility_name,
                severity=message.severity_name,
            )
            return

        # Apply transformations if specified in the filter
        transformed_message = message
        if result.transforms:
            transformed_message = self.transformer.transform(message, result.transforms)

        # Forward to destinations
        for dest_name in result.destinations:
            output = self.outputs.get(dest_name)
            if output:
                success = await output.send_with_retry(transformed_message)
                if not success:
                    self.log.warning(
                        "Failed to forward message",
                        destination=dest_name,
                        facility=message.facility_name,
                    )

    async def start(self) -> None:
        """Start the forwarder service."""
        self.log.info("Starting syslog forwarder")
        self._running = True

        # Start metrics server
        if self.config.service.metrics.enabled:
            self._start_metrics_server()

        # Connect outputs
        for name, output in self.outputs.items():
            try:
                await output.connect()
            except Exception as e:
                self.log.error("Failed to connect output", destination=name, error=str(e))

        # Start inputs
        for inp in self.inputs:
            await inp.start()

        self.log.info(
            "Syslog forwarder started",
            inputs=len(self.inputs),
            destinations=len(self.outputs),
            filters=len(self.config.filters),
        )

    async def stop(self) -> None:
        """Stop the forwarder service."""
        self.log.info("Stopping syslog forwarder")
        self._running = False

        # Stop inputs first
        for inp in self.inputs:
            await inp.stop()

        # Disconnect outputs
        for output in self.outputs.values():
            await output.disconnect()

        # Stop metrics server
        self._stop_metrics_server()

        self.log.info("Syslog forwarder stopped")

    def _start_metrics_server(self) -> None:
        """Start the Prometheus metrics HTTP server."""
        metrics_config = self.config.service.metrics

        class Handler(MetricsHandler):
            """Custom handler that also serves /health."""

            def do_GET(self) -> None:
                if self.path == "/health":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(b"OK")
                else:
                    super().do_GET()

        try:
            self._metrics_server = HTTPServer(
                (metrics_config.host, metrics_config.port),
                Handler,
            )
            self._metrics_thread = Thread(target=self._metrics_server.serve_forever, daemon=True)
            self._metrics_thread.start()
            self.log.info("Metrics server started", address=metrics_config.address)
        except Exception as e:
            self.log.error("Failed to start metrics server", error=str(e))

    def _stop_metrics_server(self) -> None:
        """Stop the metrics HTTP server."""
        if self._metrics_server:
            self._metrics_server.shutdown()
            self._metrics_server = None
            self._metrics_thread = None

    async def run_forever(self) -> None:
        """Run the forwarder until interrupted."""
        await self.start()

        # Set up signal handlers
        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()

        def signal_handler() -> None:
            self.log.info("Received shutdown signal")
            stop_event.set()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, signal_handler)

        # Wait for shutdown signal
        await stop_event.wait()
        await self.stop()
