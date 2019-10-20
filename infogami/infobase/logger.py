"""
Infobase Logger module.

Infogami log file is a stream of events where each event is a dictionary represented in JSON format having keys [`action`, `site`, `data`].

   * action: Name of action being logged. Possible values are write, new_account and update_object.
   * site: Name of site
   * data: data associated with the event. This data is used for replaying that action.

Log files are circulated on daily basis. Default log file format is $logroot/yyyy/mm/dd.log.
"""

import datetime
import os
import threading
import time

import simplejson


def synchronize(f):
    """decorator to synchronize a method."""
    def g(self, *a, **kw):
        if not getattr(self, '_lock'):
            self._lock = threading.Lock()

        self._lock.acquire()
        try:
            return f(self, *a, **kw)
        finally:
            self._lock.release()

    return f

def to_timestamp(iso_date_string):
    """
        >>> t = '2008-01-01T01:01:01.010101'
        >>> to_timestamp(t).isoformat()
        '2008-01-01T01:01:01.010101'
    """
    #@@ python datetime module is ugly.
    #@@ It takes so much of work to create datetime from isoformat.
    date, time = iso_date_string.split('T', 1)
    y, m, d = date.split('-')
    H, M, S = time.split(':')
    S, ms = S.split('.')
    return datetime.datetime(*map(int, [y, m, d, H, M, S, ms]))

class DummyLogger:
    def __init__(self, *a, **kw):
        pass

    def on_write(self, *a, **kw):
        pass

    def on_new_account(self, *a, **kw):
        pass

    def on_update_account(self, *a, **kw):
        pass

    def __call__(self, event):
        pass

class Logger:
    def __init__(self, root, compress=False):
        self.root = root
        if compress:
            import gzip
            self.extn = ".log.gz"
            self._open = gzip.open
        else:
            self.extn = ".log"
            self._open = open

    def get_path(self, timestamp=None):
        timestamp = timestamp or datetime.datetime.utcnow()
        date = timestamp.date()
        return os.path.join(self.root, "%02d" % date.year, "%02d" % date.month, "%02d" % date.day) + self.extn

    def __call__(self, event):
        import web
        data = event.data.copy()
        event.timestamp = event.timestamp or datetime.datetime.utcnow()
        if event.name in ['write', 'save', 'save_many']:
            name = event.name
            data['ip'] = event.ip
            data['author'] = event.username
        elif event.name == 'register':
            # data will already contain username, password, email and displayname
            name = "new_account"
            data['ip'] = event.ip
        elif event.name == 'update_user':
            name = "update_account"
            data['ip'] = event.ip
        elif event.name.startswith("store."):
            name = event.name
        else:
            return

        self.write(name, event.sitename, event.timestamp, data)

    @synchronize
    def write(self, action, sitename, timestamp, data):
        path = self.get_path(timestamp)
        dir = os.path.dirname(path)
        if not os.path.exists(dir):
            os.makedirs(dir)
        f = self._open(path, 'a')
        f.write(simplejson.dumps(dict(action=action, site=sitename, timestamp=timestamp.isoformat(), data=data)))
        f.write('\n')
        f.flush()
        #@@ optimize: call fsync after all modifications are written instead of calling for every modification
        os.fsync(f.fileno())
        f.close()

if __name__ == '__main__':
    import doctest
    doctest.testmod()
