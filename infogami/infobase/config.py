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

user_root = "/user/"

# @@ Hack to execute some code when infobase is created.
# @@ This will be replaced with a better method soon.
startup_hook = None

bind_address = None
port = 5964
fastcgi = False

# earlier there used to be a machine_comment column in version table.
# Set this flag to True to continue to use that field in earlier installations.
use_machine_comment = False

# bot column is added transaction table to mark edits by bot. Flag to enable/disable this feature.
use_bot_column = True

verify_user_email = False


def get(key, default=None):
    return globals().get(key, default)
