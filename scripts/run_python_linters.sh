#!/usr/bin/env bash
# Used for GitHub Actions
set -e -v

# Run linters and formatters
black --skip-string-normalization --check .
codespell --ignore-words-list=asend,alo,ba,spawnve
flake8 . --count --ignore=E203,E402,E722,E731,F811,F841,W503 \
         --max-complexity=43 --max-line-length=175 --show-source --statistics
# exit-zero treats all errors as warnings.  The GitHub editor is 127 chars wide
flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics
# FIXME: Remove `|| true` once the code is isort compliant
isort --check-only --profile black . || true
mypy --install-types --non-interactive .

# FIXME: Remove `|| true`
shopt -s globstar && pyupgrade --py39-plus **/*.py || true
