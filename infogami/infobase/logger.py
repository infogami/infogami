"""
Infobase Logger module.

The following are logged:
    * new object creations and object modifications
    * new account registrations and account modifications

Log files are circulated on daily basis. Default log file format is $logroot/yyyy/mm/dd.log.
"""

import datetime, time
import simplejson
import os

def to_date(iso_date_string):
    date = iso_date_string.split('T')[0]
    return datetime.datetime(*(time.strptime(date, "%Y-%m-%d")[0:6]))    

class Logger:
    def __init__(self, site, root):
        self.site = site
        self.root = root
        
    def get_path(self, timestamp=None):
        timestamp = timestamp or datetime.datetime.utcnow()
        date = timestamp.date()
        return os.path.join(self.root, "%02d" % date.year, "%02d" % date.month, "%02d.log" % date.day)
    
    def on_write(self, result):
        modified = result['created'] + result['updated']
        if not modified:
            return
        
        for m in modified:
            t = self.site.get(m)
            self.write(t._get_data())
            
    def write(self, data):
        timestamp = data.get('last_modified')
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
                
    def on_account_change(self, type, username, data):
        """
        This is called when something is changed in the any user account.
        The type must be one of "newuser", "password", "email" to specify new user registration, password change and email change.
        The data must contain email or password or both depending on the type.
        """
        #@@ may be it is better to write new user registrations in a separate log file
        #@@ It might be a security threat to expose log files to everyone.
        self.write(dict(_account=type, username=username, data=data))
