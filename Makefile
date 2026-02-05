.PHONY: help build up down logs test dev monitoring clean validate simulate

# Default target
help:
	@echo "Syslog Forwarder - Development Commands"
	@echo ""
	@echo "Build & Run:"
	@echo "  make build      - Build Docker images"
	@echo "  make up         - Start forwarder and receiver"
	@echo "  make down       - Stop all services"
	@echo "  make logs       - Show forwarder logs"
	@echo "  make logs-all   - Show all service logs"
	@echo ""
	@echo "Development:"
	@echo "  make dev        - Start development environment with hot-reload"
	@echo "  make test       - Run unit tests"
	@echo "  make validate   - Validate configuration file"
	@echo "  make simulate   - Send test syslog messages"
	@echo ""
	@echo "Monitoring:"
	@echo "  make monitoring - Start with Prometheus & Grafana"
	@echo "  make metrics    - Show current metrics"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean      - Remove containers, volumes, and logs"

# Build Docker images
build:
	docker compose build

# Start forwarder and receiver
up: build
	docker compose up -d syslog-fwd syslog-receiver
	@echo ""
	@echo "Services started:"
	@echo "  - Syslog input: localhost:5514 (UDP/TCP)"
	@echo "  - Metrics: http://localhost:9090/metrics"
	@echo ""
	@echo "Send test message: make simulate"

# Stop all services
down:
	docker compose down

# Show forwarder logs
logs:
	docker compose logs -f syslog-fwd

# Show all logs
logs-all:
	docker compose logs -f

# Show receiver logs (forwarded messages)
logs-receiver:
	docker compose exec syslog-receiver cat /var/log/all.log 2>/dev/null || echo "No logs yet"

# Development environment with hot-reload
dev:
	docker compose --profile dev up -d syslog-receiver
	docker compose --profile dev run --rm dev

# Run unit tests
test:
	uv run pytest tests/ -v

# Validate configuration
validate:
	uv run syslog-fwd validate -c config.yaml

# Send test syslog messages
simulate:
	@echo "Sending test messages to localhost:5514..."
	uv run syslog-fwd simulate -d localhost:5514 -p udp -n 5
	@echo ""
	@echo "Check forwarded messages: make logs-receiver"

# Start with monitoring stack
monitoring: build
	docker compose --profile monitoring up -d
	@echo ""
	@echo "Services started:"
	@echo "  - Syslog input: localhost:5514 (UDP/TCP)"
	@echo "  - Metrics: http://localhost:9090/metrics"
	@echo "  - Prometheus: http://localhost:9091"
	@echo "  - Grafana: http://localhost:3000 (admin/admin)"

# Show current metrics
metrics:
	@curl -s http://localhost:9090/metrics 2>/dev/null | grep -E "^syslog_" || echo "Metrics not available. Is the forwarder running?"

# Clean up everything
clean:
	docker compose --profile monitoring --profile dev --profile test down -v --remove-orphans
	rm -rf sandbox/syslog-receiver/logs/*
	@echo "Cleaned up containers, volumes, and logs"

# Quick test: up, simulate, check logs
quicktest: up
	@sleep 2
	@make simulate
	@sleep 1
	@make logs-receiver
