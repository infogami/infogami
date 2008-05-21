"""Infobase configuration."""

# IP address of machines which can be trusted for doing admin tasks
trusted_machines = ["127.0.0.1"]

# default size of cache
default_cache_size = 1000

# set size of individual caches
site_cache_size = 10
key_cache_size = None
thing_cache_size = None
things_cache_size = None
versions_cache_size = None

# set this to log dir to enable logging
logroot = None

# query_timeout in milli seconds.
query_timeout = None