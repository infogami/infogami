import os
import web
import infogami
import config

def infogamiroot():
    return os.path.dirname(infogami.__file__)

def createdb():
    if 'db' in web.ctx:
        web.ctx.db.close()
        web.unload()
        import gc
        gc.collect()

    db = config.db_parameters['db']
    print >> web.debug, 'createdb', db
    os.system('dropdb %s; createdb %s; psql %s < %s/tdb/schema.sql' % (db, db, db, infogamiroot()))

def run_action(name, args=[]):
    infogami.config.__dict__.update(config.__dict__)
    # hack
    infogami.config.plugins.append('pages')
    infogami._setup()
    infogami.run_action(name, args)

def tempdir():
    import tempfile
    return tempfile.mkdtemp()

def write_tempfile(text):
    import tempfile
    path = tempfile.mktemp()
    f = open(path, 'w')
    f.write(text)
    f.close()
    return path
