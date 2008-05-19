"""
Infobase Logger module.

The following are logged:
    * new_object
    * update_object
    * new_account
    * update_account

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

def to_date(iso_date_string):
    date = iso_date_string.split('T')[0]
    return datetime.datetime(*(time.strptime(date, "%Y-%m-%d")[0:6]))    
            
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
    def __init__(self, site, root):
        self.site = site
        self.root = root
        
    def get_path(self, timestamp=None):
        timestamp = timestamp or datetime.datetime.utcnow()
        date = timestamp.date()
        return os.path.join(self.root, "%02d" % date.year, "%02d" % date.month, "%02d.log" % date.day)
    
    @synchronize
    def on_write(self, result, comment, machine_comment, author, ip):
        modified = result['created'] + result['updated']
        if not modified:
            return
            
        d = dict(action='new_object', comment=comment, machine_comment=machine_comment, author=author and author.key, ip=ip)
        for key in result['created']:
            object = self.site.get(key)
            self.write(dict(d, object=object._get_data()), timestamp=object.last_modified)
        
        d['action'] = 'update_object'
        for key in result['updated']:
            object = self.site.get(key)
            self.write(dict(d, object=object._get_data()), timestamp=object.last_modified)
                
    def write(self, data, timestamp=None):
        timestamp = timestamp and to_date(timestamp)
        path = self.get_path(timestamp)
        dir = os.path.dirname(path)
        if not os.path.exists(dir):
            os.makedirs(dir)
        f = open(path, 'a')
        f.write(simplejson.dumps(data))
        f.write('\n')
        f.flush()
        #@@ optimize: call fsync after all modifications are written instead of calling for every modification
        os.fsync(f.fileno())
        f.close()
    
    @synchronize    
    def on_new_account(self, username, email, password):
        self.write(dict(action='new_account', username=username, email=email, password=password))
        
    @synchronize
    def on_update_account(self, username, email, password):
        # email will be be None when password is updated and password is None when email is updated.
        d = dict(action='update_account', username=username)
        if email:
            d['email'] = email
        if password:
            d['password'] = password
        self.write(d)
