"""
TDB Logger.
"""

import threading
import os

logfile = None

# log msg for one transaction is stored in this file and on commit,
# this file's content is appended to the logfile and this file is removed.
txfilename = "transaction.log"
txfile = None

lock = threading.RLock()

def set_logfile(f):
    global logfile
    logfile = f
    
def transact():
    if logfile:
        _acquire()
    
def commit():
    if logfile:
        f = open(txfilename)
        msg = f.read()
        f.close()
    
        logfile.write(msg)
        os.fsync(logfile.fileno())

        _release()

def rollback():
    if logfile:
        _release()

def log(_name, id, **kw):
    """Logs one item."""
    if logfile:
        msg = format(_name, id, kw)
        txfile.write(msg)
        txfile.flush()
        os.fsync(txfile.fileno())

def _acquire():
    """Acquires the lock and creates transaction log file."""
    global txfile
    lock.acquire()
    txfile = open(txfilename, 'w')

def _release():
    """Deletes the transaction log file and releases the lock."""
    global txfile
    txfile.close()
    txfile = None
    os.remove(txfilename)
    lock.release()
        
def is_consistant():
    """Checks if the log file is consistant state."""
    return os.path.exists(txfilename)

def format(_name, id, kw):
    s = ""
    s += "%s %d\n" % (_name, id)
    for k, v in kw.iteritems():
        s += "%s: %s\n" % (_keyescape(k), _encode(v))
    s += '\n'
    return s

def _keyescape(key):
    key = key.replace('\\', r'\\')
    key = key.replace('\n', r'\n')
    key = key.replace('\t', r'\t')
    key = key.replace(':', r'\:')
    return key

def _encode(value):
    from tdb import Thing
    def xrepr(s): return "'" + repr('"' + s)[2:]

    if isinstance(value, list):
        return '[%s]' % ", ".join([encode(v) for v in value])
    elif isinstance(value, (str, unicode)):
        return xrepr(value.encode('utf-8'))
    elif isinstance(value, (int, long)):
        return repr(int(value))
    elif isinstance(value, Thing):
        return 't' + _encode(value.id)
    else:
        return repr(value)        