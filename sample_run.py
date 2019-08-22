"""
Sample run.py
"""
from __future__ import print_function
import infogami

## your db parameters
infogami.config.db_parameters = dict(dbn='postgres', db="infogami", user='yourname', pw='')

## site name 
infogami.config.site = 'infogami.org'
infogami.config.admin_password = "admin123"

## add additional plugins and plugin path
#infogami.config.plugin_path += ['plugins']
#infogami.config.plugins += ['search']

def createsite():
    import web
    from infogami.infobase import dbstore, infobase, config, server
    web.config.db_parameters = infogami.config.db_parameters
    web.config.db_printing = True
    web.ctx.ip = '127.0.0.1'

    server.app.request('/')
    schema = dbstore.Schema()
    store = dbstore.DBStore(schema)
    ib = infobase.Infobase(store, config.secret_key)
    ib.create(infogami.config.site)

if __name__ == "__main__":
    import sys

    if '--schema' in sys.argv:
        from infogami.infobase.dbstore import Schema
        print(Schema().sql())
    elif '--createsite' in sys.argv:
        createsite()
    else:
        infogami.run()

