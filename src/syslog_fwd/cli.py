"""CLI for syslog-fwd."""

import asyncio
import sys
from pathlib import Path

import click
import structlog
import yaml

from . import __version__
from .config import Config, load_config
from .forwarder import SyslogForwarder


def configure_logging(level: str) -> None:
    """Configure structlog for console output."""
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


@click.group()
@click.version_option(version=__version__, prog_name="syslog-fwd")
def main() -> None:
    """Syslog Forwarder - Lightweight syslog forwarding with simple YAML configuration."""
    pass


@main.command()
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default="config.yaml",
    help="Path to configuration file.",
)
def run(config_path: Path) -> None:
    """Run the syslog forwarder."""
    try:
        config = load_config(config_path)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error loading configuration: {e}", err=True)
        sys.exit(1)

    configure_logging(config.service.log_level)
    log = structlog.get_logger()

    log.info("Configuration loaded", config_file=str(config_path))

    forwarder = SyslogForwarder(config)

    try:
        asyncio.run(forwarder.run_forever())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.error("Forwarder error", error=str(e))
        sys.exit(1)


@main.command()
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default="config.yaml",
    help="Path to configuration file.",
)
def validate(config_path: Path) -> None:
    """Validate configuration file."""
    try:
        config = load_config(config_path)
        click.echo(f"✓ Configuration is valid: {config_path}")
        click.echo(f"  Inputs: {len(config.inputs)}")
        click.echo(f"  Transforms: {len(config.transforms)}")
        click.echo(f"  Filters: {len(config.filters)}")
        click.echo(f"  Destinations: {len(config.destinations)}")

        # Show summary
        if config.inputs:
            click.echo("\n  Inputs:")
            for inp in config.inputs:
                click.echo(f"    - {inp.name}: {inp.protocol.value}://{inp.address}")

        if config.transforms:
            click.echo("\n  Transforms:")
            for t in config.transforms:
                ops = []
                if t.remove_fields:
                    ops.append(f"remove:{','.join(t.remove_fields)}")
                if t.set_fields:
                    ops.append(f"set:{','.join(t.set_fields.keys())}")
                if t.mask_patterns:
                    ops.append(f"mask:{len(t.mask_patterns)} patterns")
                if t.message_replace:
                    ops.append("replace")
                if t.message_prefix:
                    ops.append("prefix")
                if t.message_suffix:
                    ops.append("suffix")
                click.echo(f"    - {t.name}: {', '.join(ops) if ops else '(no-op)'}")

        if config.filters:
            click.echo("\n  Filters:")
            for f in config.filters:
                if f.action == "forward":
                    transforms_str = f" [transforms: {', '.join(f.transforms)}]" if f.transforms else ""
                    click.echo(f"    - {f.name}: → {', '.join(f.destinations or [])}{transforms_str}")
                else:
                    click.echo(f"    - {f.name}: [DROP]")

        if config.destinations:
            click.echo("\n  Destinations:")
            for d in config.destinations:
                click.echo(f"    - {d.name}: {d.protocol.value}://{d.address} ({d.format.value})")

    except FileNotFoundError as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"✗ Configuration error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.option("--dest", "-d", required=True, help="Destination address (host:port).")
@click.option("--protocol", "-p", type=click.Choice(["udp", "tcp"]), default="udp", help="Protocol.")
@click.option("--count", "-n", default=10, help="Number of messages to send.")
@click.option("--rate", "-r", default=1.0, help="Messages per second.")
@click.option(
    "--facility",
    "-f",
    type=click.Choice(["auth", "daemon", "local0", "local1", "user"]),
    default="local0",
    help="Syslog facility.",
)
@click.option(
    "--severity",
    "-s",
    type=click.Choice(["debug", "info", "warning", "err", "crit"]),
    default="info",
    help="Syslog severity.",
)
def simulate(
    dest: str, protocol: str, count: int, rate: float, facility: str, severity: str
) -> None:
    """Send test syslog messages."""
    import socket
    import time
    from datetime import datetime

    from .config import FACILITY_MAP, SEVERITY_MAP

    if ":" not in dest:
        click.echo("Error: Destination must be in format host:port", err=True)
        sys.exit(1)

    host, port_str = dest.rsplit(":", 1)
    port = int(port_str)

    fac_num = FACILITY_MAP.get(facility, 16)  # local0 default
    sev_num = SEVERITY_MAP.get(severity, 6)  # info default
    pri = (fac_num * 8) + sev_num

    click.echo(f"Sending {count} messages to {protocol}://{dest}")
    click.echo(f"Facility: {facility} ({fac_num}), Severity: {severity} ({sev_num})")

    if protocol == "udp":
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    else:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(10)
            sock.connect((host, port))
        except socket.timeout:
            click.echo(f"Error: Connection timeout to {dest}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"Error: Failed to connect: {e}", err=True)
            sys.exit(1)

    interval = 1.0 / rate if rate > 0 else 0
    sent = 0

    try:
        for i in range(count):
            ts = datetime.now().strftime("%b %d %H:%M:%S")
            hostname = "simulator"
            msg = f"<{pri}>{ts} {hostname} syslog-fwd-simulator[{i}]: Test message {i + 1}/{count}"

            if protocol == "udp":
                sock.sendto(msg.encode(), (host, port))
            else:
                sock.send((msg + "\n").encode())

            sent += 1
            if interval > 0 and i < count - 1:
                time.sleep(interval)

        click.echo(f"✓ Sent {sent} messages")
    except Exception as e:
        click.echo(f"Error after {sent} messages: {e}", err=True)
        sys.exit(1)
    finally:
        sock.close()


@main.command("export")
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default="config.yaml",
    help="Path to configuration file.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output file (default: stdout).",
)
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["syslog-ng"]),
    default="syslog-ng",
    help="Output format.",
)
def export_config(config_path: Path, output: Path | None, output_format: str) -> None:
    """Export configuration to other formats (e.g., syslog-ng)."""
    from .export_syslogng import export_to_syslogng

    try:
        config = load_config(config_path)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error loading configuration: {e}", err=True)
        sys.exit(1)

    if output_format == "syslog-ng":
        result = export_to_syslogng(config)
    else:
        click.echo(f"Unsupported format: {output_format}", err=True)
        sys.exit(1)

    if output:
        output.write_text(result)
        click.echo(f"✓ Exported to {output}")
    else:
        click.echo(result)


@main.command("init")
@click.option("--output", "-o", type=click.Path(path_type=Path), default="config.yaml")
def init_config(output: Path) -> None:
    """Generate example configuration file."""
    example_config = """\
# Syslog Forwarder Configuration
version: "1"

# Input listeners
inputs:
  - name: udp-514
    protocol: udp
    address: "0.0.0.0:5514"  # Use non-privileged port for testing

  - name: tcp-514
    protocol: tcp
    address: "0.0.0.0:5514"

# Filter rules (first match wins)
filters:
  # Forward auth logs to SIEM
  - name: security-logs
    match:
      facility: [auth, authpriv]
      severity: [warning, err, crit, alert, emerg]
    destinations: [siem]

  # Drop debug messages
  - name: drop-debug
    match:
      severity: [debug]
    action: drop

  # Forward everything else to central logging
  - name: default
    destinations: [central]

# Output destinations
destinations:
  - name: siem
    protocol: tcp
    address: "siem.example.com:514"
    format: rfc5424

  - name: central
    protocol: udp
    address: "logs.example.com:514"
    format: rfc3164

# Service settings
service:
  log_level: info
  metrics:
    enabled: true
    address: "0.0.0.0:9090"
"""

    if output.exists():
        if not click.confirm(f"File {output} exists. Overwrite?"):
            sys.exit(0)

    output.write_text(example_config)
    click.echo(f"✓ Created example configuration: {output}")
    click.echo("\nEdit the file to configure your inputs, filters, and destinations.")
    click.echo("Then run: syslog-fwd validate -c config.yaml")


if __name__ == "__main__":
    main()
