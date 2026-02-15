# Contributing to bac-py

Thank you for your interest in contributing to bac-py! This guide will help you
get started.

## Development Setup

**Requirements:** Python 3.13+, [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/jscott3201/bac-py.git
cd bac-py
uv sync --group dev
```

## Quality Gates

All contributions must pass the full quality gate before merging. Run everything
at once with:

```bash
make check    # lint + typecheck + test + docs
```

Or run individually:

```bash
make lint       # ruff check + format verification
make typecheck  # mypy
make test       # pytest (~6,400 unit tests)
make docs       # sphinx-build
```

To auto-fix formatting and lint issues:

```bash
make fix
```

## Code Standards

- **Formatter/Linter:** [Ruff](https://docs.astral.sh/ruff/) -- config in
  `ruff.toml`. Line length 99, double quotes, PEP 257 docstrings.
- **Type checking:** [mypy](https://mypy-lang.org/) in strict mode.
- **Testing:** [pytest](https://docs.pytest.org/) with `asyncio_mode = "auto"`
  -- async tests work without the `@pytest.mark.asyncio` decorator.
- **Zero runtime dependencies:** The core library must not add runtime
  dependencies. Optional extras (`serialization`, `secure`) are acceptable.

## Making Changes

1. **Create a branch** from `main` for your work.
2. **Write tests** for new functionality. We maintain ~99% coverage.
3. **Update documentation** if your change affects public API, adds examples, or
   changes behavior. Update `docs/guide/*.rst`, `docs/features.rst`, and
   `examples/` as needed. New example scripts in `examples/` are auto-discovered
   by the test suite.
4. **Update the changelog.** Add an entry to `CHANGELOG.md` under
   `[Unreleased]` following [Keep a Changelog](https://keepachangelog.com/)
   categories: Added, Changed, Deprecated, Removed, Fixed, Security.
5. **Run `make check`** and ensure everything passes before opening a PR.

## Pull Request Process

1. Fill out the PR template with a summary of your changes and a test plan.
2. Ensure CI passes (lint, typecheck, test, docs).
3. Keep PRs focused -- one logical change per PR.
4. Be responsive to review feedback.

## Project Structure

```
src/bac_py/       # Library source code
tests/            # Unit tests (mirrors src/ layout)
examples/         # Runnable example scripts (auto-tested)
docs/             # Sphinx documentation
docker/           # Docker integration test scenarios
scripts/          # Local benchmark scripts
```

See the [documentation](https://jscott3201.github.io/bac-py/) for architecture
details and API reference.

## Reporting Issues

- Use the [bug report](https://github.com/jscott3201/bac-py/issues/new?template=bug_report.yml)
  template for bugs.
- Use the [feature request](https://github.com/jscott3201/bac-py/issues/new?template=feature_request.yml)
  template for enhancements.
- For security vulnerabilities, see [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions will be licensed under the
[MIT License](LICENSE).
