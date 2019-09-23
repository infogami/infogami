"""
Infobase.
"""
from __future__ import print_function
import sys
import web

from infogami.infobase import config, infobase, logger, logreader

commands = {}
def command(f):
    commands[f.__name__] = f
    return f

@command
def help():
    """Prints this help."""
    print("Infobase help\n\nCommands:\n")
    for name, c in commands.items():
        print("%-20s %s" % (name, c.__doc__))

@command
def createsite(sitename, admin_password):
    """Creates a new site. Takes 2 arguments sitename and admin_password."""
    web.load()
    import infobase
    infobase.Infobase().create_site(sitename, admin_password)

@command
def startserver(*args):
    """Starts the infobase server at port 8080. An optional port argument can be specified to run the server at a different port."""
    sys.argv = [sys.argv[0]] + list(args)
    import server
    server.run()

def run():
    if len(sys.argv) > 1:
        action = sys.argv[1]
    else:
        action = 'startserver'

    return commands[action](*sys.argv[2:])

if __name__ == "__main__":
    import os
    dbname = os.environ.get('INFOBASE_DB', 'infobase')
    web.config.db_printing = True
    web.config.db_parameters = dict(dbn='postgres', db=dbname)
    run()
