from infogami.infobase import dbstore, client, server

import os
import web

db_parameters = dict(
    host='postgres',
    dbn='postgres',
    db='infobase_test',
    user=os.getenv('USER'),
    pw='',
    pooling=False,
)


@web.memoize
def recreate_database():
    """drop and create infobase_test database.

    This function is memoized to recreate the db only once per test session.
    """
    assert os.system('dropdb   --host=postgres infobase_test') == 0
    assert os.system('createdb --host=postgres infobase_test') == 0

    db = web.database(**db_parameters)

    schema = dbstore.default_schema or dbstore.Schema()
    sql = str(schema.sql())
    db.query(sql)


def setup_db(mod):
    recreate_database()

    mod.db_parameters = db_parameters.copy()
    web.config.db_parameters = db_parameters.copy()
    mod.db = web.database(**db_parameters)

    mod._create_database = dbstore.create_database
    dbstore.create_database = lambda *a, **kw: mod.db

    mod._tx = mod.db.transaction()


def teardown_db(mod):
    dbstore.create_database = mod._create_database

    mod._tx.rollback()

    mod.db.ctx.clear()
    try:
        del mod.db
    except:
        pass


def setup_conn(mod):
    setup_db(mod)
    web.config.db_parameters = mod.db_parameters
    web.config.debug = False
    mod.conn = client.LocalConnection()


def teardown_conn(mod):
    teardown_db(mod)
    try:
        del mod.conn
    except:
        pass


def setup_server(mod):
    # clear unwanted state
    web.ctx.clear()

    server._infobase = None  # clear earlier reference, if any.
    server.get_site("test")  # initialize server._infobase
    mod.site = server._infobase.create("test")  # create a new site


def teardown_server(mod):
    server._infobase = None

    try:
        del mod.site
    except:
        pass


def setup_site(mod):
    web.config.db_parameters = db_parameters.copy()
    setup_db(mod)
    setup_server(mod)


def teardown_site(mod):
    teardown_server(mod)
    teardown_db(mod)
