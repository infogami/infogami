from infogami.infobase import dbstore

import os
import web

def setup_db(mod):
    os.system('dropdb infobase_test; createdb infobase_test')
    mod.db = web.database(dbn='postgres', db='infobase_test', user=os.getenv('USER'), pw='')
    
    schema = dbstore.default_schema or dbstore.Schema()
    sql = str(schema.sql())
    mod.db.query(sql)
    
def teardown_db(mod):
    mod.db.ctx.clear()
    mod.db = None