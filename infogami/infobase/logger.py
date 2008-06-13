"""
Infobase Logger module.

Infogami log file is a stream of events where each event is a dictionary represented in JSON format having keys [`action`, `site`, `data`].

   * action: Name of action being logged. Possible values are write, new_account and update_object.
   * site: Name of site
   * data: data associated with the event. This data is used for replaying that action.

Log files are circulated on daily basis. Default log file format is $logroot/yyyy/mm/dd.log.
"""

import datetime, time
import _json as simplejson
import os
import threading

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
    
    def on_write(self, site, timestamp, query, result, comment, machine_comment, author, ip):
        d = dict(query=query, comment=comment, machine_comment=machine_comment, author=author and author.key, ip=ip)
        self.write('write', site.name, timestamp, d)
    
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
    
    def on_new_account(self, site, timestamp, username, displayname, email, password, ip):
        self.write('new_account', site.name, timestamp, data=dict(username=username, displayname=displayname, email=email, password=password, ip=ip))
        
    def on_update_account(self, site, timestamp, username, email, password, ip):
        # email will be be None when password is updated and password is None when email is updated.
        d = dict(username=username)
        if email:
            d['email'] = email
        if password:
            d['password'] = password
        self.write('update_account', site.name, timestamp, d)
        
if __name__ == '__main__':
    import doctest
    doctest.testmod()
