import web
import os

# https://stackoverflow.com/questions/58518448
web.template.ALLOWED_AST_NODES.append('Constant')

INDEXED_DATATYPES = ["str", "int", "ref"]


class Schema:
    """Schema to map <type, datatype, key> to database table.

    >>> schema = Schema()
    >>> schema.add_entry('page_str', '/type/page', 'str', None)
    >>> schema.find_table('/type/page', 'str', 'title')
    'page_str'
    >>> schema.find_table('/type/article', 'str', 'title')
    'datum_str'
    """

    def __init__(self, multisite=False):
        self.entries = []
        self.sequences = {}
        self.prefixes = set()
        self.multisite = multisite
        self._table_cache = {}

    def add_entry(self, table, type, datatype, name):
        entry = web.storage(table=table, type=type, datatype=datatype, name=name)
        self.entries.append(entry)

    def add_seq(self, type, pattern='/%d'):
        self.sequences[type] = pattern

    def get_seq(self, type):
        if type in self.sequences:
            # name is 'type_page_seq' for type='/type/page'
            name = type[1:].replace('/', '_') + '_seq'
            return web.storage(type=type, pattern=self.sequences[type], name=name)

    def add_table_group(self, prefix, type, datatypes=None):
        datatypes = datatypes or INDEXED_DATATYPES
        for d in datatypes:
            self.add_entry(prefix + "_" + d, type, d, None)

        self.prefixes.add(prefix)

    def find_table(self, type, datatype, name):
        if datatype not in INDEXED_DATATYPES:
            return None

        def f():
            def match(a, b):
                return a is None or a == b

            for e in self.entries:
                if (
                    match(e.type, type)
                    and match(e.datatype, datatype)
                    and match(e.name, name)
                ):
                    return e.table
            return 'datum_' + datatype

        key = type, datatype, name
        if key not in self._table_cache:
            self._table_cache[key] = f()
        return self._table_cache[key]

    def find_tables(self, type):
        return [self.find_table(type, d, None) for d in INDEXED_DATATYPES]

    def sql(self):
        prefixes = sorted(list(self.prefixes) + ['datum'])
        sequences = [self.get_seq(type).name for type in self.sequences]

        path = os.path.join(os.path.dirname(__file__), 'schema.sql')
        t = web.template.frender(path)

        self.add_table_group("datum", None)

        tables = sorted({(e.table, e.datatype) for e in self.entries})
        web.template.Template.globals['dict'] = dict
        web.template.Template.globals['enumerate'] = enumerate
        return t(tables, sequences, self.multisite)

    def list_tables(self):
        self.add_table_group("datum", None)
        tables = sorted({e.table for e in self.entries})
        return tables

    def __str__(self):
        lines = [f"{e.table}\t{e.type}\t{e.datatype}\t{e.name}" for e in self.entries]
        return "\n".join(lines)
