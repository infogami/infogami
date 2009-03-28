"""Infobase configuration."""

# IP address of machines which can be trusted for doing admin tasks
trusted_machines = ["127.0.0.1"]

# default size of cache
cache_size = 1000

secret_key = "bzuim9ws8u"

# set this to log dir to enable logging
logroot = None
compress_log = False

# query_timeout in milli seconds.
query_timeout = "60000"

#@@ Hack to execute some code when infobase is created. 
#@@ This will be replaced with a better method soon.
startup_hook = None
