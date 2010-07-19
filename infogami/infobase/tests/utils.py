from infogami.infobase import dbstore, client, server

import os
import web

db_parameters = dict(dbn='postgres', db='infobase_test', user=os.getenv('USER'), pw='', pooling=False)

def setup_db(mod):
    assert os.system('dropdb infobase_test; createdb infobase_test') == 0
    mod.db_parameters = db_parameters.copy()    
    mod.db = web.database(**mod.db_parameters)

    schema = dbstore.default_schema or dbstore.Schema()
    sql = str(schema.sql())
    mod.db.query(sql)
    
def teardown_db(mod):
    mod.db.ctx.clear()
    del mod.db
    
def setup_conn(mod):
    setup_db(mod)
    web.config.db_parameters = mod.db_parameters
    mod.conn = client.LocalConnection()

def teardown_conn(mod):
    teardown_db(mod)
    del mod.conn 
    
def setup_server(mod):
    # clear unwanted state
    web.ctx.clear()
    
    server._infobase = None # clear earlier reference, if any.
    server.get_site("test") # initialize server._infobase
    mod.site = server._infobase.create("test") # create a new site

def teardown_server(mod):
    server._infobase.store.db.ctx.clear()
    server._infobase = None
    del mod.site

def setup_site(mod):
    web.config.db_parameters = db_parameters.copy()
    setup_db(mod)
    setup_server(mod)
    
def teardown_site(mod):
    teardown_server(mod)
    teardown_db(mod)
