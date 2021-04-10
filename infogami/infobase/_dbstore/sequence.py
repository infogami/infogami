"""High-level sequence API.
"""


class SequenceImpl:
    def __init__(self, db):
        self.db = db
        self.listener = None

    def set_listener(self, f):
        self.listener = f

    def fire_event(self, event_name, name, value):
        self.listener and self.listener("seq.set", {"name": name, "value": value})

    def get_value(self, name):
        try:
            return self.db.query("SELECT * FROM seq WHERE name=$name", vars=locals())[
                0
            ].value
        except IndexError:
            return 0

    def next_value(self, name, increment=1):
        try:
            tx = self.db.transaction()
            d = self.db.query(
                "SELECT * FROM seq WHERE name=$name FOR UPDATE", vars=locals()
            )
            if d:
                value = d[0].value + 1
                self.db.update("seq", value=value, where="name=$name", vars=locals())
            else:
                value = 1
                self.db.insert("seq", name=name, value=value)
        except:
            tx.rollback()
            raise
        else:
            tx.commit()
        return value

    def set_value(self, name, value):
        try:
            tx = self.db.transaction()
            d = self.db.query(
                "SELECT * FROM seq WHERE name=$name FOR UPDATE", vars=locals()
            )
            if d:
                self.db.update("seq", value=value, where="name=$name", vars=locals())
            else:
                self.db.insert("seq", name=name, value=value)
        except:
            tx.rollback()
            raise
        else:
            tx.commit()
        return value
