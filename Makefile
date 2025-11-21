.PHONY: lint lint-fix format format-check test cichecks help

help:
	@echo "Available commands:"
	@echo "  make lint         - Check code style with ruff"
	@echo "  make lint-fix     - Auto-fix linting issues"
	@echo "  make format       - Format code with ruff"
	@echo "  make format-check - Check formatting without changing files"
	@echo "  make test         - Run tests"
	@echo "  make cichecks     - Run all CI checks (test, lint, format-check)"

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

