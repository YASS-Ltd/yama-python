# yama-python. Install just: https://just.systems/man/en/

schema_url := "https://app.yamasystems.com/api/v2/schema/"
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
check: lint typecheck test build docs-build

# Build the sdist and wheel, then import the wheel in a clean environment
[group('release')]
build:
    rm -rf dist
    uv build
    uv run --isolated --no-project --with dist/*.whl python -c "import yama; print('yama', yama.__version__)"

# Serve the docs at http://localhost:8000, rebuilding on changes
[group('docs')]
docs:
    uv run zensical serve

# Build the docs into site/, failing on any warning, such as a broken link
[group('docs')]
docs-build:
    uv run zensical build --strict --clean

# Show how the published schema differs from the vendored copy
[group('schema')]
schema-diff:
    curl -fsS {{schema_url}} | diff -u {{schema_file}} - && echo "Schema is up to date."

# Replace the vendored schema with the published one
[group('schema')]
schema-pull:
    curl -fsS {{schema_url}} -o {{schema_file}}

# Read-only unless YAMA_LIVE_WRITE=1, which briefly creates a real door code: never set it
# against production.
[group('release')]
[doc("Run the live tests against a non-production Yama API, with YAMA_API_KEY set")]
test-live base_url="" *args:
    YAMA_LIVE_BASE_URL={{quote(base_url)}} uv run pytest -m live -rs {{args}}

# Cut a release from a clean main: just release [--dry-run] [X.Y.Z]
[group('release')]
release *args:
    uv run python -m tools.release {{args}}
