"""
Log file reader.
"""
import os
import itertools
import datetime
import time
import web

import _json as simplejson
import logger

def daterange(begin, end=None):
    """Return an iterator over dates from begin to end (inclusive). 
    If end is not specified, end is taken as utcnow."""
    end = end or datetime.datetime.utcnow().date()
    
    while begin.date() <= end:
        yield begin
        begin = begin + datetime.timedelta(1) # add one day
        
def ijoin(iters):
    """Joins given list of iterators as a single iterator.
    
        >>> list(ijoin([xrange(0, 5), xrange(10, 15)]))
        [0, 1, 2, 3, 4, 10, 11, 12, 13, 14]
    """
    return (x for it in iters for x in it)

class LogReader:
    def __init__(self, logroot):
        self.root = logroot
        self.extn = ".log"
                
    def get_path(self, date):
        return os.path.join(self.root, "%02d" % date.year, "%02d" % date.month, "%02d" % date.day) + self.extn
        
    def read_from(self, timestamp, infinite=False):
        """Returns iterator over the log starting from the specified timestamp.
        If argument 'infinite' is true, the iterable never terminates.
        It instead expects the log to keep growing as new log records
        arrive, so on reaching end of log it blocks until more data
        becomes available.   If 'infinite' is false, generator terminates
        when it reaches end of the log.
        """
        def readfile(f):
            for line in f:
                entry = simplejson.loads(line)
                entry = web.storage(entry)
                entry.timestamp = logger.to_timestamp(entry.timestamp)
                yield entry
                
        def read(date):
            logfile = self.get_path(date)
            if os.path.exists(logfile):
                return readfile(open(logfile))
            else:
                return []
                    
        if infinite:
            log = readfile(self.create_logfile(timestamp))
        else:
            log = ijoin(read(date) for date in daterange(timestamp))
        return itertools.dropwhile(lambda entry: entry.timestamp <= timestamp, log)

    def create_logfile(self, timestamp):
        return LogFile(self.root, timestamp)

class RsyncLogReader(LogReader):
    def __init__(self, rsync_root, dir, waittime=60):
        LogReader.__init__(self, dir)
        self.rsync_root = rsync_root
        if not self.rsync_root.endswith('/'):
            self.rsync_root += '/'
        self.dir = dir
        self.waittime = waittime

    def create_logfile(self, timestamp):
        return RsyncLogFile(self.rsync_root, self.dir, self.waittime)

    def rsync(self):
        cmd = "rsync -r %s %s" % (self.rsync_root, self.dir)
        print cmd
        os.system(cmd)

    def read_from(self, timestamp, infinite=False):
        if infinite:
            while True:
                self.rsync()
                #@@ calling read_from again and again is not efficient
                for entry in LogReader.read_from(self, timestamp):
                    timestamp = entry.timestamp
                    yield entry

                time.sleep(self.waittime)
        else:
            self.rsync()
            for entry in LogReader.read_from(self, timestamp):
                yield entry

class LogFile:
    """Single file interface over entire log files.
    Iterator on this file never terminates. It instead keep waiting for more log data to come.
    """
    def __init__(self, root, begin_date, waittime=1):
        """Creates a Logfile to read the log from the specified begin date."""
        self.root = root
        self.waittime = waittime
        end_of_world = datetime.date(9999, 12, 31)
        self.dates = daterange(begin_date, end_of_world)        
        self.extn = ".log"
        self.advance()
    
    def advance(self):
        """Move to the next file."""
        self.current_date = self.dates.next()
        self.file = self.openfile()
        
    def openfile(self):
        date = self.current_date
        path = os.path.join(self.root, "%02d" % date.year, "%02d" % date.month, "%02d" % date.day) + self.extn
        if os.path.exists(path):
            return open(path)
        
    def wait(self):
        """Called when there are no chars left in the file. 
        It waits if the current file is the latest, otherwise it advances 
        to the next file.
        """
        assert self.current_date.date() <= datetime.datetime.utcnow().date()
        if self.current_date.date() < datetime.datetime.utcnow().date():
            self.advance()
        else:
            self.sleep(self.waittime)
            if self.file is None:
                self.file = self.openfile()

    def sleep(self, seconds):
        time.sleep(seconds)
                
    def read(self, n):
        return "".join(self.readchar() for i in xrange(n))
    
    def readchar(self):
        """Read a single char from log. If no character is available 
        (when end of log is reached), it blocks till more data is avalable."""
        c = self.file and self.file.read(1)
        while not c:
            self.wait()
            c = self.file and self.file.read(1)
        return c
        
    def __iter__(self):
        """Returns an infinite stream over the log."""
        def charstream():
            # generate a sequence of the lines in fd, never
            # terminating.  On reaching end of fd, 
            # sleep til more characters are available.
            while True:
                c = self.file and self.file.read(1)
                if c: yield c
                else: self.wait()
                
        while True:
            yield ''.join(iter(self.readchar, '\n')) 
    
    xreadlines = __iter__

class LogPlayback:
    """Playback log"""
    def __init__(self, infobase):
        self.infobase = infobase
        
    def playback_stream(self, entries):
        """Playback all entries from the specified log stream."""
        for entry in entries:
            self.playback(entry)
            
    def playback(self, entry):
        """Playback one log entry."""
        #@@ hack to disable permission check
        web.ctx.infobase_bootstrap = True
        site = self.infobase.get_site(entry.site)
        return getattr(self, entry.action)(site, entry.timestamp, entry.data)
    
    def write(self, site, timestamp, data):
        d = web.storage(data)
        author = d.author and site.withKey(d.author)
        site._write(d.query, comment=d.comment, machine_comment=d.comment, ip=d.ip, author=author, timestamp=timestamp)
                
    def new_account(self, site, timestamp, data):
        d = web.storage(data)
        a = site.get_account_manager()
        a.register(d.username, d.displayname, d.email, d.password, password_encrypted=True, timestamp=timestamp)
        
    def update_account(self, site, timestamp, data):
        d = web.storage(data)
        user = site.withKey(d.username)
        a = site.get_account_manager()
        a._update_user(user, 
            encrypted_password=d.get('password'), 
            email=d.get('email'),
            timestamp=timestamp)
    
if __name__ == "__main__":
    import doctest
    doctest.testmod()
