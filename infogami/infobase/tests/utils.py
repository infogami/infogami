from infogami.infobase import dbstore, client

import os
import web

def setup_db(mod):
    os.system('dropdb infobase_test; createdb infobase_test')
    mod.db_parameters = dict(dbn='postgres', db='infobase_test', user=os.getenv('USER'), pw='', pooling=False)
    
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