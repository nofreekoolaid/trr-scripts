.PHONY: lint lint-fix format format-check test cichecks tvl avgtvl help

help:
	@echo "Available commands:"
	@echo "  make lint         - Check code style with ruff"
	@echo "  make lint-fix     - Auto-fix linting issues"
	@echo "  make format       - Format code with ruff"
	@echo "  make format-check - Check formatting without changing files"
	@echo "  make test         - Run tests"
	@echo "  make cichecks     - Run all CI checks (test, lint, format-check)"
	@echo "  make tvl          - Get TVL data (use: make tvl PROTOCOL=euler START=2025-01-01 END=2025-01-15)"
	@echo "  make avgtvl       - Get average TVL (use: make avgtvl PROTOCOL=euler START=2025-01-01 END=2025-01-15)"
	@echo ""
	@echo "TVL Examples:"
	@echo "  make tvl PROTOCOL=euler START=2025-01-01 END=2025-01-15"
	@echo "  make tvl PROTOCOL=aave START=2025-01-01 END=2025-01-31"
	@echo "  make tvl PROTOCOL=uniswap START=2024-12-01 END=2024-12-31 OPTS='--no-extrapolate'"
	@echo "  make tvl PROTOCOL=euler START=2025-01-01 END=2025-01-15 OPTS='--mean'"
	@echo ""
	@echo "Average TVL Examples:"
	@echo "  make avgtvl PROTOCOL=euler START=2025-01-01 END=2025-01-15"
	@echo "  make avgtvl PROTOCOL=aave START=2025-01-01 END=2025-01-31"
	@echo "  make avgtvl PROTOCOL=compound START=2024-01-01 END=2024-12-31"

lint:
	uv run ruff check .

lint-fix:
	uv run ruff check --fix .

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

test:
	uv run python -m unittest discover -s . -p 'test_*.py'

cichecks:
	@echo "=== CI CHECKS START ==="; \
	echo ""; \
	echo "--- SECTION: Tests ---"; \
	uv run python -m unittest discover -s . -p 'test_*.py' 2>&1; \
	TEST_EXIT=$$?; \
	if [ $$TEST_EXIT -eq 0 ]; then \
		echo "STATUS: TESTS_PASSED"; \
	else \
		echo "STATUS: TESTS_FAILED"; \
	fi; \
	echo ""; \
	echo "--- SECTION: Linting ---"; \
	uv run ruff check . 2>&1; \
	LINT_EXIT=$$?; \
	if [ $$LINT_EXIT -eq 0 ]; then \
		echo "STATUS: LINT_PASSED"; \
	else \
		echo "STATUS: LINT_FAILED"; \
	fi; \
	echo ""; \
	echo "--- SECTION: Format Check ---"; \
	uv run ruff format --check . 2>&1; \
	FORMAT_EXIT=$$?; \
	if [ $$FORMAT_EXIT -eq 0 ]; then \
		echo "STATUS: FORMAT_PASSED"; \
	else \
		echo "STATUS: FORMAT_FAILED"; \
	fi; \
	echo ""; \
	echo "=== CI CHECKS SUMMARY ==="; \
	if [ $$TEST_EXIT -eq 0 ] && [ $$LINT_EXIT -eq 0 ] && [ $$FORMAT_EXIT -eq 0 ]; then \
		echo "RESULT: PASSED"; \
		exit 0; \
	else \
		echo "RESULT: FAILED"; \
		exit 1; \
	fi

# Get TVL data for a protocol
# Usage: make tvl PROTOCOL=euler START=2025-01-01 END=2025-01-15
# Optional: OPTS='--no-extrapolate' or OPTS='--mean'
tvl:
	@if [ -z "$(PROTOCOL)" ] || [ -z "$(START)" ] || [ -z "$(END)" ]; then \
		echo "Error: Missing required parameters"; \
		echo "Usage: make tvl PROTOCOL=<protocol> START=<start-date> END=<end-date>"; \
		echo "Example: make tvl PROTOCOL=euler START=2025-01-01 END=2025-01-15"; \
		echo "Optional: Add OPTS='--mean' or OPTS='--no-extrapolate'"; \
		exit 1; \
	fi
	@uv run python avg_tvls.py $(PROTOCOL) $(START) $(END) $(OPTS)

# Get average TVL for a protocol (with interpolation/extrapolation)
# Usage: make avgtvl PROTOCOL=euler START=2025-01-01 END=2025-01-15
# Optional: OPTS='--no-extrapolate' to disable extrapolation
avgtvl:
	@if [ -z "$(PROTOCOL)" ] || [ -z "$(START)" ] || [ -z "$(END)" ]; then \
		echo "Error: Missing required parameters"; \
		echo "Usage: make avgtvl PROTOCOL=<protocol> START=<start-date> END=<end-date>"; \
		echo "Example: make avgtvl PROTOCOL=euler START=2025-01-01 END=2025-01-15"; \
		echo "Optional: Add OPTS='--no-extrapolate' to disable extrapolation"; \
		exit 1; \
	fi
	@uv run python avg_tvls.py $(PROTOCOL) $(START) $(END) --mean $(OPTS)
