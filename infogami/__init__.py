import web
import config

usage = """
Infogami

list of commands:

run             start the webserver
dbupgrade       upgrade the database
help            show this
"""

def _setup():
    if config.db_parameters is None:
        raise Exception('infogami.config.db_parameters is not specified')

    if config.site is None:
        raise Exception('infogami.config.site is not specified')
        
    web.webapi.internalerror = config.internalerror
    web.config.db_parameters = config.db_parameters

def db_upgrade():
    from infogami.utils import dbsetup
    dbsetup.apply_upgrades()

def start_server():
    _setup()
    from infogami.utils import delegate
    delegate._load()
    web.run(delegate.urls, delegate.__dict__)

def run():
    import sys
    if len(sys.argv) == 1 or sys.argv[1] == 'run':
        # web.py expects port as argv[1]
        sys.argv = [sys.argv[0]]
        start_server()
    elif sys.argv[1] == 'dbupgrade':
        db_upgrade()
    elif sys.argv[1] == 'help':
        print usage
    else:
        print >> sys.stderr, 'unknown command', sys.argv[1]
        print usage
