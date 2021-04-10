#!/usr/bin/env bash
# Used for GitHub actions

# Run linters and formatters
black --check .
codespell . --ignore-words-list=ba,referer --quiet-level=2
flake8 .
  \ --count
  \ --select=C,E5,E9,F4,F6,F7,F82
  \ --max-complexity=43
  \ --max-line-length=233
  \ --show-source
  \ --statistics
# exit-zero treats all errors as warnings.  The GitHub editor is 127 chars wide
flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics
# FIXME: Remove `|| true` once the code is isort compliant
isort --check-only --profile black . || true
mypy .

# FIXME: Remove `|| true`
shopt -s globstar && pyupgrade --py38-plus **/*.py || true
