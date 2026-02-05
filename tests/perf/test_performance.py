#!/usr/bin/env python3
"""Performance test for syslog-fwd with field removal transforms.

Sends 10,000 messages and measures throughput and latency.
"""

import asyncio
import socket
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import click
import httpx


@dataclass
class PerfResults:
    """Performance test results."""

    total_messages: int
    duration_seconds: float
    messages_per_second: float
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    messages_received: int
    messages_forwarded: int
    messages_dropped: int
    errors: int


@dataclass
class IntervalStats:
    """Stats for a single reporting interval."""

    interval_num: int
    timestamp: str
    messages_sent: int
    duration_seconds: float
    messages_per_second: float
    messages_received: int
    messages_forwarded: int
    success_rate: float


def generate_rfc5424_message(seq: int, proc_id: str = "1234", msg_id: str = "ID47") -> bytes:
    """Generate an RFC 5424 syslog message with proc_id and msg_id fields."""
    # Priority: facility=local0 (16), severity=info (6) => 16*8+6 = 134
    pri = 134
    version = 1
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    hostname = "perftest"
    app_name = "benchmark"
    structured_data = "-"
    msg = f"Performance test message {seq}/10000 - testing field removal transform"

    # RFC 5424: <PRI>VERSION TIMESTAMP HOSTNAME APP-NAME PROCID MSGID STRUCTURED-DATA MSG
    syslog_msg = f"<{pri}>{version} {timestamp} {hostname} {app_name} {proc_id} {msg_id} {structured_data} {msg}"
    return syslog_msg.encode("utf-8")


async def send_messages_udp(
    host: str, port: int, count: int, batch_size: int = 100
) -> tuple[float, list[float]]:
    """Send messages via UDP and return duration and per-batch latencies."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)

    latencies: list[float] = []
    start_time = time.perf_counter()

    for batch_start in range(0, count, batch_size):
        batch_end = min(batch_start + batch_size, count)
        batch_start_time = time.perf_counter()

        for i in range(batch_start, batch_end):
            msg = generate_rfc5424_message(i + 1)
            try:
                sock.sendto(msg, (host, port))
            except BlockingIOError:
                await asyncio.sleep(0.001)
                sock.sendto(msg, (host, port))

        batch_latency = (time.perf_counter() - batch_start_time) * 1000
        latencies.append(batch_latency)

        # Small yield to allow event loop processing
        if batch_start % 1000 == 0:
            await asyncio.sleep(0.001)

    duration = time.perf_counter() - start_time
    sock.close()

    return duration, latencies


async def send_messages_tcp(
    host: str, port: int, count: int, batch_size: int = 100, timeout: float = 30.0
) -> tuple[float, list[float]]:
    """Send messages via TCP and return duration and per-batch latencies."""
    latencies: list[float] = []

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
    except asyncio.TimeoutError:
        raise ConnectionError(f"Timeout connecting to {host}:{port}")

    start_time = time.perf_counter()

    try:
        for batch_start in range(0, count, batch_size):
            batch_end = min(batch_start + batch_size, count)
            batch_start_time = time.perf_counter()

            for i in range(batch_start, batch_end):
                msg = generate_rfc5424_message(i + 1)
                writer.write(msg + b"\n")

            await writer.drain()

            batch_latency = (time.perf_counter() - batch_start_time) * 1000
            latencies.append(batch_latency)

            # Small yield to allow event loop processing
            if batch_start % 1000 == 0:
                await asyncio.sleep(0.001)

    finally:
        writer.close()
        await writer.wait_closed()

    duration = time.perf_counter() - start_time
    return duration, latencies


async def get_metrics(metrics_url: str, timeout: float = 10.0) -> dict[str, float]:
    """Fetch Prometheus metrics from the forwarder."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.get(metrics_url)
            resp.raise_for_status()
        except Exception as e:
            return {"error": str(e)}

    metrics: dict[str, float] = {}
    for line in resp.text.split("\n"):
        if line.startswith("#") or not line.strip():
            continue
        try:
            name, value = line.rsplit(" ", 1)
            # Extract base metric name
            base_name = name.split("{")[0]
            metrics[base_name] = metrics.get(base_name, 0) + float(value)
        except (ValueError, IndexError):
            continue

    return metrics


def calculate_results(
    count: int,
    duration: float,
    latencies: list[float],
    metrics_before: dict[str, float],
    metrics_after: dict[str, float],
) -> PerfResults:
    """Calculate performance results from raw data."""
    # Per-message latencies (approximate from batch)
    batch_size = 100
    per_msg_latencies = [lat / batch_size for lat in latencies for _ in range(batch_size)]
    per_msg_latencies = per_msg_latencies[:count]  # Trim to exact count

    received_before = metrics_before.get("syslog_messages_received_total", 0)
    received_after = metrics_after.get("syslog_messages_received_total", 0)
    forwarded_before = metrics_before.get("syslog_messages_forwarded_total", 0)
    forwarded_after = metrics_after.get("syslog_messages_forwarded_total", 0)
    dropped_before = metrics_before.get("syslog_messages_dropped_total", 0)
    dropped_after = metrics_after.get("syslog_messages_dropped_total", 0)

    sorted_latencies = sorted(per_msg_latencies)

    return PerfResults(
        total_messages=count,
        duration_seconds=duration,
        messages_per_second=count / duration if duration > 0 else 0,
        avg_latency_ms=statistics.mean(per_msg_latencies) if per_msg_latencies else 0,
        p50_latency_ms=sorted_latencies[int(len(sorted_latencies) * 0.50)] if sorted_latencies else 0,
        p95_latency_ms=sorted_latencies[int(len(sorted_latencies) * 0.95)] if sorted_latencies else 0,
        p99_latency_ms=sorted_latencies[int(len(sorted_latencies) * 0.99)] if sorted_latencies else 0,
        messages_received=int(received_after - received_before),
        messages_forwarded=int(forwarded_after - forwarded_before),
        messages_dropped=int(dropped_after - dropped_before),
        errors=count - int(received_after - received_before),
    )


def print_results(results: PerfResults, protocol: str) -> None:
    """Print formatted test results."""
    click.echo("\n" + "=" * 60)
    click.echo(f"PERFORMANCE TEST RESULTS ({protocol.upper()})")
    click.echo("=" * 60)
    click.echo(f"\n📊 Throughput:")
    click.echo(f"   Total messages:     {results.total_messages:,}")
    click.echo(f"   Duration:           {results.duration_seconds:.2f}s")
    click.echo(f"   Messages/second:    {results.messages_per_second:,.0f}")

    click.echo(f"\n⏱️  Latency (per message, estimated):")
    click.echo(f"   Average:            {results.avg_latency_ms:.3f}ms")
    click.echo(f"   P50:                {results.p50_latency_ms:.3f}ms")
    click.echo(f"   P95:                {results.p95_latency_ms:.3f}ms")
    click.echo(f"   P99:                {results.p99_latency_ms:.3f}ms")

    click.echo(f"\n📈 Forwarder Metrics:")
    click.echo(f"   Received:           {results.messages_received:,}")
    click.echo(f"   Forwarded:          {results.messages_forwarded:,}")
    click.echo(f"   Dropped:            {results.messages_dropped:,}")
    click.echo(f"   Errors:             {results.errors:,}")

    # Success rate
    if results.total_messages > 0:
        success_rate = (results.messages_forwarded / results.total_messages) * 100
        click.echo(f"   Success rate:       {success_rate:.1f}%")

    click.echo("=" * 60 + "\n")


async def run_long_test(
    host: str,
    port: int,
    protocol: str,
    duration_minutes: float,
    rate: float,
    report_interval: int,
    metrics_url: str,
) -> None:
    """Run long-duration test with periodic reporting."""
    import signal

    duration_seconds = duration_minutes * 60
    interval_messages = int(rate * report_interval)
    stop_requested = False

    def handle_signal(signum: int, frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True
        click.echo("\n⚠️  Stop requested, finishing current interval...")

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    click.echo(f"\n🚀 Starting long-running {protocol.upper()} test...")
    click.echo(f"   Duration: {duration_minutes:.1f} minutes")
    click.echo(f"   Target rate: {rate:.0f} msg/s")
    click.echo(f"   Report every: {report_interval}s ({interval_messages:,} messages)")
    click.echo("\n   Press Ctrl+C to stop gracefully\n")

    # Print header
    click.echo(
        f"{'Interval':>8} | {'Time':>12} | {'Sent':>10} | {'Rate':>10} | "
        f"{'Received':>10} | {'Forwarded':>10} | {'Success':>8}"
    )
    click.echo("-" * 90)

    all_stats: list[IntervalStats] = []
    total_sent = 0
    total_received = 0
    total_forwarded = 0
    start_time = time.perf_counter()
    interval_num = 0

    # Get initial metrics
    metrics_prev = await get_metrics(metrics_url)
    if "error" in metrics_prev:
        metrics_prev = {}

    while not stop_requested:
        elapsed = time.perf_counter() - start_time
        if elapsed >= duration_seconds:
            break

        interval_num += 1
        interval_start = time.perf_counter()

        # Send messages for this interval
        if protocol == "udp":
            _, _ = await send_messages_udp(host, port, interval_messages, batch_size=100)
        else:
            _, _ = await send_messages_tcp(host, port, interval_messages, batch_size=100)

        interval_duration = time.perf_counter() - interval_start
        total_sent += interval_messages

        # Wait for the rest of the interval if we finished early
        remaining = report_interval - interval_duration
        if remaining > 0:
            await asyncio.sleep(remaining)

        # Get metrics
        metrics_now = await get_metrics(metrics_url)
        if "error" in metrics_now:
            metrics_now = metrics_prev.copy()

        received = int(
            metrics_now.get("syslog_messages_received_total", 0)
            - metrics_prev.get("syslog_messages_received_total", 0)
        )
        forwarded = int(
            metrics_now.get("syslog_messages_forwarded_total", 0)
            - metrics_prev.get("syslog_messages_forwarded_total", 0)
        )
        total_received += received
        total_forwarded += forwarded

        success_rate = (forwarded / interval_messages * 100) if interval_messages > 0 else 0
        actual_rate = interval_messages / interval_duration if interval_duration > 0 else 0

        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        stats = IntervalStats(
            interval_num=interval_num,
            timestamp=timestamp,
            messages_sent=interval_messages,
            duration_seconds=interval_duration,
            messages_per_second=actual_rate,
            messages_received=received,
            messages_forwarded=forwarded,
            success_rate=success_rate,
        )
        all_stats.append(stats)

        # Print interval stats
        click.echo(
            f"{interval_num:>8} | {timestamp:>12} | {interval_messages:>10,} | "
            f"{actual_rate:>10,.0f} | {received:>10,} | {forwarded:>10,} | "
            f"{success_rate:>7.1f}%"
        )

        metrics_prev = metrics_now

    # Print summary
    total_duration = time.perf_counter() - start_time
    click.echo("\n" + "=" * 90)
    click.echo("LONG-RUNNING TEST SUMMARY")
    click.echo("=" * 90)
    click.echo(f"\n📊 Overall Statistics:")
    click.echo(f"   Total duration:     {total_duration / 60:.1f} minutes ({total_duration:.0f}s)")
    click.echo(f"   Intervals:          {len(all_stats)}")
    click.echo(f"   Total sent:         {total_sent:,}")
    click.echo(f"   Total received:     {total_received:,}")
    click.echo(f"   Total forwarded:    {total_forwarded:,}")

    if total_sent > 0:
        overall_success = (total_forwarded / total_sent) * 100
        overall_rate = total_sent / total_duration if total_duration > 0 else 0
        click.echo(f"   Average rate:       {overall_rate:,.0f} msg/s")
        click.echo(f"   Overall success:    {overall_success:.2f}%")

    if all_stats:
        rates = [s.messages_per_second for s in all_stats]
        click.echo(f"\n📈 Rate Statistics:")
        click.echo(f"   Min rate:           {min(rates):,.0f} msg/s")
        click.echo(f"   Max rate:           {max(rates):,.0f} msg/s")
        click.echo(f"   Avg rate:           {statistics.mean(rates):,.0f} msg/s")
        if len(rates) > 1:
            click.echo(f"   Std dev:            {statistics.stdev(rates):,.0f} msg/s")

    click.echo("=" * 90 + "\n")


@click.command()
@click.option("--host", "-h", default="localhost", help="Forwarder host.")
@click.option("--port", "-p", default=5514, type=int, help="Forwarder port.")
@click.option("--protocol", type=click.Choice(["udp", "tcp", "both"]), default="udp", help="Protocol to test.")
@click.option("--count", "-n", default=10000, type=int, help="Number of messages to send (burst mode).")
@click.option("--duration", "-d", default=0.0, type=float, help="Test duration in minutes (long-running mode).")
@click.option("--rate", "-r", default=1000.0, type=float, help="Target messages per second (long-running mode).")
@click.option("--report-interval", default=10, type=int, help="Reporting interval in seconds (long-running mode).")
@click.option("--metrics-url", "-m", default="http://localhost:9090/metrics", help="Prometheus metrics URL.")
@click.option("--warmup", "-w", default=100, type=int, help="Warmup messages before test.")
@click.option("--timeout", "-t", default=60.0, type=float, help="Test timeout in seconds (burst mode).")
def main(
    host: str,
    port: int,
    protocol: str,
    count: int,
    duration: float,
    rate: float,
    report_interval: int,
    metrics_url: str,
    warmup: int,
    timeout: float,
) -> None:
    """Run performance test for syslog-fwd.

    Two modes available:

    BURST MODE (default): Send a fixed number of messages as fast as possible.
      Example: test_performance.py -n 10000 --protocol udp

    LONG-RUNNING MODE: Send messages at a target rate for a specified duration.
      Example: test_performance.py -d 60 -r 1000 --protocol tcp
      (runs for 60 minutes at 1000 msg/s)
    """
    # Determine mode
    long_running = duration > 0

    click.echo("=" * 60)
    click.echo("SYSLOG FORWARDER PERFORMANCE TEST")
    click.echo("=" * 60)
    click.echo(f"\nConfiguration:")
    click.echo(f"  Target:          {host}:{port}")
    click.echo(f"  Protocol:        {protocol}")

    if long_running:
        click.echo(f"  Mode:            LONG-RUNNING")
        click.echo(f"  Duration:        {duration:.1f} minutes")
        click.echo(f"  Target rate:     {rate:,.0f} msg/s")
        click.echo(f"  Report interval: {report_interval}s")
    else:
        click.echo(f"  Mode:            BURST")
        click.echo(f"  Message count:   {count:,}")
        click.echo(f"  Warmup:          {warmup} messages")

    click.echo(f"  Transform:       remove 2 fields (proc_id, msg_id)")
    click.echo(f"  Metrics URL:     {metrics_url}")

    if long_running:
        # Long-running mode
        proto = "tcp" if protocol == "tcp" else "udp"  # Default to UDP for "both"
        if protocol == "both":
            click.echo("\n⚠️  Long-running mode only supports single protocol, using UDP")

        try:
            asyncio.run(
                run_long_test(
                    host, port, proto, duration, rate, report_interval, metrics_url
                )
            )
        except KeyboardInterrupt:
            click.echo("\n⚠️  Test interrupted")
        except Exception as e:
            click.echo(f"\n❌ Test failed: {e}", err=True)
            raise SystemExit(1)
    else:
        # Burst mode (original behavior)
        async def run_burst_test() -> None:
            protocols_to_test = ["udp", "tcp"] if protocol == "both" else [protocol]

            for proto in protocols_to_test:
                click.echo(f"\n🚀 Starting {proto.upper()} test...")

                # Warmup
                if warmup > 0:
                    click.echo(f"   Warming up with {warmup} messages...")
                    if proto == "udp":
                        await send_messages_udp(host, port, warmup)
                    else:
                        await send_messages_tcp(host, port, warmup, timeout=timeout)
                    await asyncio.sleep(1)  # Let forwarder process warmup

                # Get metrics before test
                click.echo("   Fetching baseline metrics...")
                metrics_before = await get_metrics(metrics_url)
                if "error" in metrics_before:
                    click.echo(f"   ⚠️  Could not fetch metrics: {metrics_before['error']}")
                    metrics_before = {}

                # Run test
                click.echo(f"   Sending {count:,} messages...")
                if proto == "udp":
                    test_duration, latencies = await send_messages_udp(host, port, count)
                else:
                    test_duration, latencies = await send_messages_tcp(
                        host, port, count, timeout=timeout
                    )

                # Wait for processing
                click.echo("   Waiting for processing to complete...")
                await asyncio.sleep(2)

                # Get metrics after test
                metrics_after = await get_metrics(metrics_url)
                if "error" in metrics_after:
                    click.echo(f"   ⚠️  Could not fetch metrics: {metrics_after['error']}")
                    metrics_after = {}

                # Calculate and print results
                results = calculate_results(
                    count, test_duration, latencies, metrics_before, metrics_after
                )
                print_results(results, proto)

        try:
            asyncio.run(asyncio.wait_for(run_burst_test(), timeout=timeout * 2))
        except asyncio.TimeoutError:
            click.echo(f"\n❌ Test timed out after {timeout * 2}s", err=True)
            raise SystemExit(1)
        except KeyboardInterrupt:
            click.echo("\n⚠️  Test interrupted")
            raise SystemExit(1)
        except Exception as e:
            click.echo(f"\n❌ Test failed: {e}", err=True)
            raise SystemExit(1)


if __name__ == "__main__":
    main()
