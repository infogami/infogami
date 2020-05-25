"""
Infobase.
"""
from __future__ import print_function
import sys
import web

from infogami.infobase import infobase, server

commands = {}
def command(f):
    commands[f.__name__] = f
    return f

@command
def help():
    """Prints this help."""
    print("Infobase help\n\nCommands:\n")
    for name, c in list(commands.items()):
        print("%-20s %s" % (name, c.__doc__))

@command
def createsite(sitename, admin_password):
    """Creates a new site. Takes 2 arguments sitename and admin_password."""
    web.load()
    infobase.Infobase().create_site(sitename, admin_password)

@command
def startserver(*args):
    """Starts the infobase server at port 8080. An optional port argument can be specified to run the server at a different port."""
    sys.argv = [sys.argv[0]] + list(args)
    server.run()

def run():
    action = sys.argv[1] if len(sys.argv) > 1 else 'startserver'
    return commands[action](*sys.argv[2:])

if __name__ == "__main__":
    import os
    dbname = os.environ.get('INFOBASE_DB', 'infobase')
    web.config.db_printing = True
    web.config.db_parameters = dict(dbn='postgres', db=dbname)
    run()
