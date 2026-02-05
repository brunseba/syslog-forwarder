# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-02-05

### Added
- Initial release of syslog-fwd
- UDP and TCP input listeners with asyncio
- RFC 3164 and RFC 5424 message parsing
- Filter engine with facility, severity, hostname, and message pattern matching
- Message transformations (remove fields, set fields, mask patterns, replace, prefix/suffix)
- UDP and TCP output forwarders with retry logic
- Prometheus metrics endpoint (`/metrics`)
- Health check endpoint (`/health`)
- CLI commands: `run`, `validate`, `simulate`, `init`, `export`
- Export configuration to syslog-ng format
- Docker support with multi-stage build
- Docker Compose sandbox with Prometheus and Grafana
- Grafana dashboard for metrics visualization
- Performance testing tools (burst and long-running modes)
- Comprehensive documentation (architecture, user guide)
- MkDocs site with Material theme

[0.1.0]: https://github.com/brunseba/syslog-forwarder/releases/tag/v0.1.0
