# yama-python. Install just: https://just.systems/man/en/

schema_url := "https://app.getyama.ca/api/v2/schema/"
schema_file := "tests/fixtures/openapi.yaml"

# List recipes
@_:
    just --list

# Install the package and dev tools
[group('setup')]
install:
    uv sync

# Run the tests, e.g. just test -k codes
[group('qa')]
test *args:
    uv run pytest {{args}}

# Run the tests with a coverage report
[group('qa')]
cov:
    uv run pytest --cov --cov-report=term-missing

# Lint and check formatting
[group('qa')]
lint:
    uv run ruff check .
    uv run ruff format --check .

# Fix lint and formatting where possible
[group('qa')]
fmt:
    uv run ruff check --fix .
    uv run ruff format .

# Type-check in strict mode
[group('qa')]
typecheck:
    uv run mypy src tests

# Everything CI runs
[group('qa')]
check: lint typecheck test build

# Build the sdist and wheel, then import the wheel in a clean environment
[group('release')]
build:
    rm -rf dist
    uv build
    uv run --isolated --no-project --with dist/*.whl python -c "import yama; print('yama', yama.__version__)"

# Show how the published schema differs from the vendored copy
[group('schema')]
schema-diff:
    curl -fsS {{schema_url}} | diff -u {{schema_file}} - && echo "Schema is up to date."

# Replace the vendored schema with the published one
[group('schema')]
schema-pull:
    curl -fsS {{schema_url}} -o {{schema_file}}
