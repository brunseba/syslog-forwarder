"""Export syslog-fwd configuration to syslog-ng format."""

from datetime import datetime

from .config import (
    Config,
    FilterConfig,
    InputConfig,
    DestinationConfig,
    TransformConfig,
    Protocol,
    SyslogFormat,
    FACILITY_MAP,
    SEVERITY_MAP,
)


def _escape_syslogng_string(s: str) -> str:
    """Escape a string for syslog-ng configuration."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _generate_header(config: Config) -> str:
    """Generate syslog-ng config header."""
    return f"""#
# syslog-ng configuration
# Generated from syslog-fwd config on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
#
# WARNING: This is an auto-generated configuration.
# Some features may require manual adjustment.
#

@version: 4.0
@include "scl.conf"

# Global options
options {{
    time-reap(30);
    mark-freq(10);
    keep-hostname(yes);
    chain-hostnames(no);
    use-dns(no);
    dns-cache(no);
    use-fqdn(no);
    create-dirs(yes);
    keep-timestamp(yes);
}};

"""


def _generate_source(inp: InputConfig, index: int) -> str:
    """Generate syslog-ng source block for an input."""
    source_name = f"s_{inp.name.replace('-', '_')}"
    host = inp.host if inp.host != "0.0.0.0" else ""
    port = inp.port

    if inp.protocol == Protocol.UDP:
        transport = "udp"
        flags = ""
    elif inp.protocol == Protocol.TCP:
        transport = "tcp"
        flags = '\n        flags(syslog-protocol)'
    else:  # TLS
        transport = "tcp"
        flags = '\n        flags(syslog-protocol)\n        tls(peer-verify(optional-untrusted))'

    ip_config = f'\n        ip("{host}")' if host else ""

    return f"""# Source: {inp.name}
source {source_name} {{
    network(
        transport("{transport}")
        port({port}){ip_config}{flags}
    );
}};

"""


def _generate_destination(dest: DestinationConfig, index: int) -> str:
    """Generate syslog-ng destination block."""
    dest_name = f"d_{dest.name.replace('-', '_')}"
    host = dest.host
    port = dest.port

    if dest.protocol == Protocol.UDP:
        transport = "udp"
    elif dest.protocol == Protocol.TCP:
        transport = "tcp"
    else:  # TLS
        transport = "tls"

    # Template based on format
    # RFC5424: <PRI>1 TIMESTAMP HOSTNAME APP-NAME PROCID MSGID STRUCTURED-DATA MSG
    if dest.format == SyslogFormat.RFC5424:
        template = '<${PRI}>1 ${ISODATE} ${HOST} ${PROGRAM} ${PID} ${MSGID} ${SDATA} ${MSG}'
    else:  # RFC3164 or AUTO
        template = '${ISODATE} ${HOST} ${PROGRAM}[${PID}]: ${MSG}'

    return f"""# Destination: {dest.name}
destination {dest_name} {{
    network(
        "{host}"
        transport("{transport}")
        port({port})
        template("{template}\\n")
    );
}};

"""


def _generate_rewrite(transform: TransformConfig, index: int) -> str:
    """Generate syslog-ng rewrite rules for a transform."""
    rewrite_name = f"r_{transform.name.replace('-', '_')}"
    rules: list[str] = []

    # Message prefix
    if transform.message_prefix:
        prefix = _escape_syslogng_string(transform.message_prefix)
        rules.append(f'        set("{prefix}${{MSG}}" value("MSG"));')

    # Message suffix
    if transform.message_suffix:
        suffix = _escape_syslogng_string(transform.message_suffix)
        rules.append(f'        set("${{MSG}}{suffix}" value("MSG"));')

    # Message replace (regex substitution)
    if transform.message_replace:
        pattern = _escape_syslogng_string(transform.message_replace.pattern)
        replacement = _escape_syslogng_string(transform.message_replace.replacement)
        rules.append(f'        subst("{pattern}", "{replacement}", value("MSG"));')

    # Mask patterns
    if transform.mask_patterns:
        for mask in transform.mask_patterns:
            pattern = _escape_syslogng_string(mask.pattern)
            replacement = _escape_syslogng_string(mask.replacement)
            rules.append(f'        subst("{pattern}", "{replacement}", value("MSG"), flags(global));')

    # Set fields
    if transform.set_fields:
        field_map = {
            "hostname": "HOST",
            "app_name": "PROGRAM",
            "proc_id": "PID",
            "msg_id": "MSGID",
        }
        for field, value in transform.set_fields.items():
            syslogng_field = field_map.get(field, field.upper())
            escaped_value = _escape_syslogng_string(value)
            rules.append(f'        set("{escaped_value}" value("{syslogng_field}"));')

    # Remove fields (set to empty or "-")
    if transform.remove_fields:
        field_map = {
            "hostname": ("HOST", ""),
            "app_name": ("PROGRAM", ""),
            "proc_id": ("PID", ""),
            "msg_id": ("MSGID", "-"),
            "structured_data": ("SDATA", "-"),
        }
        for field in transform.remove_fields:
            if field in field_map:
                syslogng_field, empty_value = field_map[field]
                rules.append(f'        set("{empty_value}" value("{syslogng_field}"));')

    if not rules:
        return ""

    rules_str = "\n".join(rules)
    return f"""# Rewrite: {transform.name}
rewrite {rewrite_name} {{
{rules_str}
}};

"""


def _generate_filter(flt: FilterConfig, transforms: dict[str, TransformConfig], index: int) -> str:
    """Generate syslog-ng filter block."""
    filter_name = f"f_{flt.name.replace('-', '_')}"
    conditions: list[str] = []

    if flt.match:
        # Facility filter
        if flt.match.facility:
            facilities = [f.value for f in flt.match.facility]
            fac_conditions = " or ".join([f'facility({f})' for f in facilities])
            if len(facilities) > 1:
                conditions.append(f"({fac_conditions})")
            else:
                conditions.append(fac_conditions)

        # Severity filter
        if flt.match.severity:
            severities = [s.value for s in flt.match.severity]
            sev_conditions = " or ".join([f'level({s})' for s in severities])
            if len(severities) > 1:
                conditions.append(f"({sev_conditions})")
            else:
                conditions.append(sev_conditions)

        # Hostname pattern
        if flt.match.hostname_pattern:
            pattern = _escape_syslogng_string(flt.match.hostname_pattern)
            conditions.append(f'host("{pattern}")')

        # Message pattern
        if flt.match.message_pattern:
            pattern = _escape_syslogng_string(flt.match.message_pattern)
            conditions.append(f'message("{pattern}")')

    if not conditions:
        # Match everything - use level range to catch all messages
        return f"""# Filter: {flt.name} (matches all)
filter {filter_name} {{
    level(debug..emerg);
}};

"""

    filter_expr = " and ".join(conditions)
    return f"""# Filter: {flt.name}
filter {filter_name} {{
    {filter_expr};
}};

"""


def _generate_log_paths(
    config: Config,
    sources: dict[str, str],
    filters: dict[str, str],
    destinations: dict[str, str],
    rewrites: dict[str, str],
) -> str:
    """Generate syslog-ng log paths."""
    output: list[str] = []
    output.append("# Log paths\n")

    # Create transform name to rewrite name mapping
    # rewrites dict has rewrite_name -> transform_name, we need the inverse
    rewrite_name_to_transform = {v: k for k, v in rewrites.items()}
    transform_to_rewrite = {
        transform_name: rewrite_name
        for transform_name, rewrite_name in [
            (t.name, f"r_{t.name.replace('-', '_')}") for t in config.transforms
        ]
        if rewrite_name in rewrites
    }

    for flt in config.filters:
        filter_name = f"f_{flt.name.replace('-', '_')}"

        # Build source list (all sources for simplicity)
        source_refs = " ".join([f"source({s});" for s in sources.keys()])

        # Filter reference
        filter_ref = f"filter({filter_name});"

        # Rewrite references for transforms
        rewrite_refs = ""
        if flt.transforms:
            rewrite_names = [transform_to_rewrite.get(t) for t in flt.transforms if t in transform_to_rewrite]
            if rewrite_names:
                rewrite_refs = " ".join([f"rewrite({r});" for r in rewrite_names if r])

        if flt.action == "drop":
            # Drop action - log to null
            output.append(f"""# Log path: {flt.name} (DROP)
log {{
    {source_refs}
    {filter_ref}
    flags(final);
}};

""")
        else:
            # Forward action
            if flt.destinations:
                dest_refs = " ".join([
                    f"destination(d_{d.replace('-', '_')});"
                    for d in flt.destinations
                ])
                rewrite_line = f"\n    {rewrite_refs}" if rewrite_refs else ""
                output.append(f"""# Log path: {flt.name}
log {{
    {source_refs}
    {filter_ref}{rewrite_line}
    {dest_refs}
    flags(final);
}};

""")

    return "".join(output)


def export_to_syslogng(config: Config) -> str:
    """Export a syslog-fwd configuration to syslog-ng format.

    Args:
        config: The syslog-fwd configuration to export.

    Returns:
        A string containing the syslog-ng configuration.
    """
    output: list[str] = []

    # Header
    output.append(_generate_header(config))

    # Track generated names
    sources: dict[str, str] = {}
    destinations: dict[str, str] = {}
    filters: dict[str, str] = {}
    rewrites: dict[str, str] = {}

    # Generate sources
    if config.inputs:
        output.append("# " + "=" * 70 + "\n")
        output.append("# Sources\n")
        output.append("# " + "=" * 70 + "\n\n")
        for i, inp in enumerate(config.inputs):
            source_name = f"s_{inp.name.replace('-', '_')}"
            sources[source_name] = inp.name
            output.append(_generate_source(inp, i))

    # Generate destinations
    if config.destinations:
        output.append("# " + "=" * 70 + "\n")
        output.append("# Destinations\n")
        output.append("# " + "=" * 70 + "\n\n")
        for i, dest in enumerate(config.destinations):
            dest_name = f"d_{dest.name.replace('-', '_')}"
            destinations[dest_name] = dest.name
            output.append(_generate_destination(dest, i))

    # Generate rewrites from transforms
    if config.transforms:
        has_rewrites = False
        rewrite_output: list[str] = []
        for i, transform in enumerate(config.transforms):
            rewrite_str = _generate_rewrite(transform, i)
            if rewrite_str:
                if not has_rewrites:
                    rewrite_output.append("# " + "=" * 70 + "\n")
                    rewrite_output.append("# Rewrites (transforms)\n")
                    rewrite_output.append("# " + "=" * 70 + "\n\n")
                    has_rewrites = True
                rewrite_name = f"r_{transform.name.replace('-', '_')}"
                rewrites[rewrite_name] = transform.name
                rewrite_output.append(rewrite_str)
        output.extend(rewrite_output)

    # Generate filters
    if config.filters:
        output.append("# " + "=" * 70 + "\n")
        output.append("# Filters\n")
        output.append("# " + "=" * 70 + "\n\n")
        transform_dict = {t.name: t for t in config.transforms}
        for i, flt in enumerate(config.filters):
            filter_name = f"f_{flt.name.replace('-', '_')}"
            filters[filter_name] = flt.name
            output.append(_generate_filter(flt, transform_dict, i))

    # Generate log paths
    if config.filters:
        output.append("# " + "=" * 70 + "\n")
        output.append("# Log paths\n")
        output.append("# " + "=" * 70 + "\n\n")
        output.append(_generate_log_paths(config, sources, filters, destinations, rewrites))

    return "".join(output)
