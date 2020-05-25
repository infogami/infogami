"""Support for multiple inserts"""

import web

def join(items, sep):
    q = web.SQLQuery('')
    for i, item in enumerate(items):
        if i: q += sep
        q += item
    return q

_pg_version = None

def get_postgres_version():    
    global _pg_version
    if _pg_version is None:
        version = web.query('SELECT version();')[0].version
        # convert "PostgreSQL 8.2.4 on ..." in to (8, 2, 4)
        tokens = version.split()[1].split('.')
        _pg_version = tuple([int(t) for t in tokens])
    return _pg_version

def multiple_insert(tablename, values, seqname=None, _test=False):
    # multiple inserts are supported only in version 8.2+
    if get_postgres_version() < (8, 2):
        result = [web.insert(tablename, seqname=seqname, **v) for v in values]
        if seqname:
            return result
        else:
            return None

    if not values:
        return []

    keys = list(values[0].keys())

    #@@ make sure all keys are valid

    # make sure all rows have same keys.
    for v in values:
        if list(v.keys()) != keys:
            raise Exception('Bad data')

    q = web.SQLQuery('INSERT INTO %s (%s) VALUES ' % (tablename, ', '.join(keys))) 

    data = []

    for row in values:
        d = join([web.SQLQuery(web.aparam(), [row[k]]) for k in keys], ', ')
        data.append('(' + d + ')')

    q += join(data, ',')

    if seqname is not False:
        if seqname is None:
            seqname = tablename + "_id_seq"
        q += "; SELECT currval('%s')" % seqname

    if _test:
        return q

    db_cursor = web.ctx.db_cursor()
    web.ctx.db_execute(db_cursor, q)

    try:
        out = db_cursor.fetchone()[0]
        out = range(out-len(values)+1, out+1)
    except Exception:
        out = None

    if not web.ctx.db_transaction: web.ctx.db.commit()
    return out

if __name__ == "__main__":
    web.config.db_parameters = dict(dbn='postgres', db='coverthing_test', user='anand', pw='')
    web.config.db_printing = True
    web.load()
    def data(id):
        return [
            dict(thing_id=id, key='isbn', value=1, datatype=1),
            dict(thing_id=id, key='source', value='amazon', datatype=1),
            dict(thing_id=id, key='image', value='foo', datatype=10)]

    ids =  multiple_insert('thing', [dict(dummy=1)] * 10)
    values = []
    for id in ids:
        values += data(id)
    multiple_insert('datum', values, seqname=False)
