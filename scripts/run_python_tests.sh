#!/usr/bin/env bash
# Used for GitHub actions

# web.py needs to find the database on a host named postgres
echo "127.0.0.1 postgres" | sudo tee -a /etc/hosts
# MUST have a --host=
psql --host=postgres --command='create database infobase_test;'

# Run tests
pytest infogami -s
pytest tests
pytest test
