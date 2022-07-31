#!/usr/bin/env bash
# Used for GitHub Actions
set -e -v

# Run linters and formatters
black --skip-string-normalization --check .
codespell  # See setup.cfg for args
flake8  # See setup.cfg for args
# FIXME: Remove `|| true` once the code is isort compliant
isort --check-only --profile black . || true
mypy --install-types --non-interactive .
shopt -s globstar && pyupgrade --py39-plus **/*.py scripts/*
