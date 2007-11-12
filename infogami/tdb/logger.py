r"""
TDB Logger.

Logger supports nested transactions. 

Log format:

    log     = item*
    item    = key " " id "\n" fields "\n"
    fields  = field*
    key     = "thing" 
            | "version"
            | "data"
        
    field   = name ": " value "\n"
    name    = <string with tab, newline and : escaped>
    value   = none
            | integer
            | utf8_string
            | reference
            | list
    
    none    = "None"
    integer = digit+
    utf8_string = <"> utf8_char* <">
    reference = t integer
    list = "[" + values + "]"
    values = empty
            | value ("," value)*
    digit = [0-9]
"""

import threading
import os
import re
import tdb
import web

logger = None

class Logger:
    def __init__(self, file, parent=None, concurrent=True):
        if isinstance(file, str):
            file = open(file, 'a')
        self.file = file
        self.parent = parent
        
        if concurrent:
            self.lock = threading.Lock()
        else:
            self.lock = None
        
    def write(self, msg):
        self.lock and self.lock.acquire()    
        try:
            self.file.write(msg)
            self.file.flush()
            os.fsync(self.file.fileno())
        finally:
            self.lock and self.lock.release()
            
    def read(self):
        return open(self.file.name).read()
        
    def destroy(self):
        os.remove(self.file.name)
        
    def __str__(self):
        return "<logger: %s (%s)>" % (self.file.name, str(self.parent))

def set_logfile(logfile):
    """Setup the global logger to write into the given logfile. 
    Logfile can be a file or a filename."""
    global logger
    logger = Logger(logfile)
    # override previous logger, if any.
    if web.ctx.get('tdb_logger'):
        web.ctx.tdb_logger = logger

def _get_logger():
    return web.ctx.get('tdb_logger', logger)
    
def log(tag, id, **kw):
    r"""
        >>> import tempfile
        >>> filename = tempfile.mktemp()
        >>> set_logfile(filename)
        >>> log('thing', 1, x=2)
        >>> open(filename).read()
        'thing 1\nx: 2\n\n'
    """    
    if logger:
        msg = format(tag, id, kw)
        _get_logger().write(msg)
        
def transact():
    """Starts a log transaction."""
    if logger:
        _push_logger()
    
def commit():
    r"""Commits a log transaction.

    >>> import tempfile
    >>> filename = tempfile.mktemp()
    >>> set_logfile(filename)
    >>> transact()
    >>> log('thing', 1, x=2)
    >>> commit()
    >>> open(filename).read()
    'thing 1\nx: 2\n\n'
    """
    xlogger = _get_logger()
    if xlogger:
        msg = xlogger.read()
        xlogger.parent.write(msg)
        _pop_logger()
    
def rollback():
    r"""Rollbacks a log transaction.

    >>> import tempfile
    >>> filename = tempfile.mktemp()
    >>> set_logfile(filename)
    >>> transact()
    >>> log('thing', 1, x=2)
    >>> rollback()
    >>> open(filename).read()
    ''
    """
    if logger:
        _pop_logger()
    
def _pop_logger():
    xlogger = _get_logger()
    web.ctx.tdb_logger = xlogger.parent
    web.ctx.tdb_log_transaction -= 1
    xlogger.destroy()

def _push_logger():
    threadname = threading.currentThread().getName()
    n = web.ctx.get('tdb_log_transaction', 0)
    filename = 'transaction_%s_%d.log' % (threadname, n)
    # It is possible that transaction log file is present because of some unfinished transaction.
    # Opening the file in write mode solves that problem.
    file = open(filename, 'w') 
    web.ctx.tdb_logger = Logger(file, _get_logger(), concurrent=False)
    web.ctx.tdb_log_transaction = n + 1

def format(tag, id, kw):
    r"""Formats log message.
        
        >>> format('thing', 2, dict(name='hello'))
        "thing 2\nname: 'hello'\n\n"
    """
    s = ""
    s += "%s %d\n" % (tag, id)
    for k, v in kw.iteritems():
        s += "%s: %s\n" % (_keyencode(k), _encode(v))
    s += '\n'
    return s

def _keyencode(key):
    r"""
        >>> _keyencode('hello')
        'hello'
        >>> _keyencode('hello:world')
        'hello\\:world'
    """
    key = key.replace('\\', r'\\')
    key = key.replace('\n', r'\n')
    key = key.replace('\t', r'\t')
    key = key.replace(':', r'\:')
    return key
    
def _keydecode(key):
    r"""
        >>> _keydecode('hello')
        'hello'
        >>> _keydecode('hello\\:world')
        'hello:world'
    """
    rx = re.compile(r"\\([\\nt:])")
    env = {
        '\\': '\\', 
        'n': '\n', 
        't': '\t', 
        ':': ':'
    }
    return rx.sub(lambda m: env[m.group(1)], key)

def xrepr(s): 
    r"""Represents a string in single quotes.
    
        >>> print xrepr('hello')
        'hello'
        >>> print xrepr("it's monday")
        'it\'s monday'
        >>> print xrepr("hello\nworld")
        'hello\nworld'
    """
    return "'" + repr('"' + s)[2:]

def _encode(value):
    r"""Encodes value.
    
        >>> _encode(1)
        '1'
        >>> _encode('hello')
        "'hello'"
        >>> _encode([1, 2, 'hello'])
        "[1, 2, 'hello']"
    """
    from tdb import Thing, LazyThing

    if isinstance(value, list):
        return '[%s]' % ", ".join([_encode(v) for v in value])
    elif isinstance(value, str):
        return xrepr(value)
    elif isinstance(value, unicode):
        return xrepr(value.encode('utf-8'))
    elif isinstance(value, (int, long)):
        return repr(int(value))
    elif isinstance(value, (Thing, LazyThing)):
        return 't' + _encode(value.id)
    else:
        return repr(value)

# for backward-compatibility
from logparser import *

if __name__ == "__main__":
    import doctest
    doctest.testmod()