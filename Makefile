##
# Makefile for ankinote-ai
#
# @file
# @version 0.3

.PHONY: test clean-test clean lint check format pre-commit help \
        build clean-dist bump-version \
        release release-check _release-guard docker-backfill \
        install install-dev

clean-test:
	rm -rf .pytest_cache
	rm -rf tests/__pycache__
	rm -rf tests/**/__pycache__
	rm -rf .coverage
	rm -rf htmlcov

test:
	uv run pytest

clean: clean-test
	rm -rf __pycache__

lint:
	uv run ruff check --fix

check:
	uv run ty check

format:
	uv run ruff format

pre-commit: format lint check

install:
	uv pip install

install-dev:
	uv pip install --group dev

clean-dist:
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf src/*.egg-info

build: clean-dist
	uv build

bump-version:
	@test -n "$(part)" || (echo "Usage: make bump-version part=<major|minor|patch>" && exit 1)
	uvx hatch version $(part)

##
# Release
#
# `make release part=<major|minor|patch>` bumps src/ankinote/__init__.py,
# commits, tags vX.Y.Z, pushes main + tag, and creates the GitHub Release.
# The Release "published" event triggers:
#   - .github/workflows/publish.yml -> PyPI (OIDC trusted publishing, no token)
#   - .github/workflows/docker.yml  -> ghcr.io + docker.io, multi-arch,
#                                      after it sees the version on PyPI
# So this target does not push to PyPI or Docker directly; CI does.
#
# Preconditions (enforced by release-check): on `main`, clean working tree,
# local main == origin/main, gh authenticated, and format/lint/type/tests green.

release-check:
	@test "$$(git rev-parse --abbrev-ref HEAD)" = "main" \
		|| { echo "release: must be on the 'main' branch"; exit 1; }
	@test -z "$$(git status --porcelain)" \
		|| { echo "release: working tree is not clean"; exit 1; }
	@command -v gh >/dev/null 2>&1 \
		|| { echo "release: gh CLI not found"; exit 1; }
	@gh auth status >/dev/null 2>&1 \
		|| { echo "release: gh CLI is not authenticated (run 'gh auth login')"; exit 1; }
	@git fetch --quiet origin main
	@test "$$(git rev-parse @)" = "$$(git rev-parse @{u})" \
		|| { echo "release: local main differs from origin/main"; exit 1; }
	uv run ruff format --check
	uv run ruff check
	uv run ty check
	uv run pytest -q

_release-guard:
	@test -n "$(part)" || { echo "Usage: make release part=<major|minor|patch>"; exit 1; }

release: _release-guard release-check
	@set -e; \
	uvx hatch version "$(part)"; \
	version="$$(sed -n 's/^__version__ = "\(.*\)"/\1/p' src/ankinote/__init__.py)"; \
	tag="v$$version"; \
	echo "Releasing $$tag"; \
	git add src/ankinote/__init__.py; \
	git commit -m "chore: bump version to $$version"; \
	git tag "$$tag"; \
	git push origin main; \
	git push origin "$$tag"; \
	rm -rf dist; \
	uv build; \
	gh release create "$$tag" --title "$$tag" --generate-notes \
		"dist/ankinote_ai-$$version-py3-none-any.whl" \
		"dist/ankinote_ai-$$version.tar.gz"; \
	echo "Published $$tag. Follow the release workflows with: gh run list"

# Rebuild and re-push a Docker image for an already-published PyPI version
# (idempotent), e.g. after a failed docker.yml run: make docker-backfill version=0.4.0
docker-backfill:
	@test -n "$(version)" || { echo "Usage: make docker-backfill version=X.Y.Z"; exit 1; }
	gh workflow run docker.yml -f version="$(version)"

help:
	@echo "Available targets:"
	@echo "  test            - Run all tests"
	@echo "  clean           - Clean up all cache files"
	@echo "  clean-test      - Clean up test cache files"
	@echo "  lint            - Run lint checks"
	@echo "  check           - Run static type checks"
	@echo "  format          - Format code with ruff"
	@echo "  pre-commit      - Run format, lint, and check"
	@echo "  build           - Build wheel and sdist"
	@echo "  bump-version    - Bump version (part=patch|minor|major)"
	@echo "  release-check   - Verify the repo is ready to release"
	@echo "  release         - Bump, tag, push, and create the GitHub Release"
	@echo "                    (part=patch|minor|major; CI then does PyPI + Docker)"
	@echo "  docker-backfill - Re-run the Docker workflow for version=X.Y.Z"
	@echo "  install         - Install dependencies"
	@echo "  install-dev     - Install development dependencies"

# end of Makefile
