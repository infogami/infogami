"""
Log file reader.
"""
from __future__ import print_function

import datetime
import glob
import itertools
import os
import time

import simplejson
import web


def nextday(date):
    return date + datetime.timedelta(1)

def daterange(begin, end=None):
    """Return an iterator over dates from begin to end (inclusive).
    If end is not specified, end is taken as utcnow."""
    end = end or datetime.datetime.utcnow().date()

    if isinstance(begin, datetime.datetime):
        begin = begin.date()
    if isinstance(end, datetime.datetime):
        end = end.date()

    while begin <= end:
        yield begin
        begin = nextday(begin)

def ijoin(iters):
    """Joins given list of iterators as a single iterator.

        >>> list(ijoin([range(0, 5), range(10, 15)]))
        [0, 1, 2, 3, 4, 10, 11, 12, 13, 14]
    """
    return (x for it in iters for x in it)

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

class LogReader:
    """
    Reads log file line by line and converts each line to python dict using simplejson.loads.
    """
    def __init__(self, logfile):
        self.logfile = logfile

    def skip_till(self, timestamp):
        """Skips the log file till the specified timestamp.
        """
        self.logfile.skip_till(timestamp.date())

        offset = self.logfile.tell()
        for entry in self:
            if entry.timestamp > timestamp:
                # timestamp of this entry is more than the required timestamp.
                # so it must be put back.
                self.logfile.seek(offset)
                break
            offset = self.logfile.tell()

    def read_entry(self):
        """Reads one entry from the log.
        None is returned when there are no more enties.
        """
        line = self.logfile.read()
        if line:
            return self._loads(line)
        else:
            return None

    def read_entries(self, n=1000000):
        """"Reads multiple enties from the log. The maximum entries to be read is specified as argument.
        """
        return [self._loads(line) for line in self.logfile.readlines(n)]

    def __iter__(self):
        for line in self.logfile:
            yield self._loads(line)

    def _loads(self, line):
        entry = simplejson.loads(line)
        entry = web.storage(entry)
        entry.timestamp = to_timestamp(entry.timestamp)
        return entry

class LogFile:
    """A file like interface over log files.

    Infobase log files are ordered by date. The presence of multiple files
    makes it difficult to read the them. This class provides a file like
    interface to make reading easier.

    Read all enties from a given timestamp::

        log = LogFile("log")
        log.skip_till(datetime.datetime(2008, 01, 01))

        for line in log:
            print log

    Read log entries in chunks::

        log = LogFile("log")
        while True:
            # read upto a maximum of 1000 lines
            lines = log.readlines(1000)
            if lines:
                do_something(lines)
            else:
                break

    Read log entries infinitely::

        log = LogFile("log")
        while True:
            # read upto a maximum of 1000 lines
            lines = log.readlines(1000)
            if lines:
                do_something(lines)
            else:
                time.sleep(10) # wait for more data to come

    Remember the offset and set the offset::

        offset = log.tell()
        log.seek(offset)
    """
    def __init__(self, root):
        self.root = root
        self.extn = ".log"

        self.file = None
        self.filelist = None
        self.current_filename = None

    def skip_till(self, date):
        """Skips till file with the specified date.
        """
        self.filelist = self.find_filelist(date)
        self.advance()

    def update(self):
        self.update_filelist(self.current_filename)

        if self.current_filename is None and self.filelist:
            self.advance()

    def update_filelist(self, current_filename=None):
        if current_filename:
            current_date = self.file2date(current_filename)
            self.filelist = self.find_filelist(nextday(current_date))
        else:
            self.filelist = self.find_filelist()

    def file2date(self, file):
        file, ext = os.path.splitext(file)
        _, year, month, day = file.rsplit('/', 3)
        return datetime.date(int(year), int(month), int(day))

    def date2file(self, date):
        return "%s/%04d/%02d/%02d.log" % (self.root, date.year, date.month, date.day)

    def advance(self):
        """Move to next file."""
        if self.filelist:
            self.current_filename = self.filelist.pop(0)
            self.file = open(self.current_filename)
            return True
        else:
            return False

    def find_filelist(self, from_date=None):
        if from_date is None:
            filelist = glob.glob('%s/[0-9][0-9][0-9][0-9]/[0-9][0-9]/[0-9][0-9].log' % self.root)
            filelist.sort()
        else:
            filelist = [self.date2file(date) for date in daterange(from_date)]
            filelist = [f for f in filelist if os.path.exists(f)]

        return filelist

    def readline(self, do_update=True):
        line = self.file and self.file.readline()
        if line:
            return line
        elif self.filelist:
            self.advance()
            return self.readline()
        else:
            if do_update:
                self.update()
                return self.readline(do_update=False)
            else:
                return ""

    def __iter__(self):
        while True:
            line = self.readline()
            if line:
                yield line
            else:
                break

    def readlines(self, n=1000000):
        """Reads multiple lines from the log file."""
        lines = self._readlines()
        if not lines:
            self.update()
            lines = self._readlines()
        return lines

    def _readlines(self, n):
        lines = []
        for i in range(n):
            line = self.readline(do_update=False)
            if not line:
                break
            lines.append(line)
        return lines

    def seek(self, offset):
        date, offset = offset.split(':')
        year, month, day = date.split("-")
        year, month, day, offset = int(year), int(month), int(day), int(offset)

        d = datetime.date(year, month, day)
        self.filelist = self.find_filelist(d)
        self.advance()

        if self.current_filename and self.file2date(self.current_filename) == d:
            self.file.seek(offset)

    def tell(self):
        if self.current_filename is None:
            return datetime.date.fromtimestamp(0).isoformat() + ":0"

        date = self.file2date(self.current_filename)
        offset = self.file.tell()
        return "%04d-%02d-%02d:%d" % (date.year, date.month, date.day, offset)

class RsyncLogFile(LogFile):
    """File interface to Remote log files. rsync is used for data transfer.

        log = RsyncLogFile("machine::module_name/path", "log")

        for line in log:
            print line
    """
    def __init__(self, rsync_root, root):
        LogFile.__init__(self, root)
        self.rsync_root = rsync_root
        if not self.rsync_root.endswith('/'):
            self.rsync_root += "/"
        self.rsync()

    def update(self):
        self.rsync()
        LogFile.update(self)

        if self.file:
            # if the current file is updated, it will be overwritten and possibly with a different inode.
            # Solving the problem by opening the file again and jumping to the current location
            file = open(self.file.name)
            file.seek(self.file.tell())
            self.file = file

    def rsync(self):
        cmd = "rsync -r %s %s" % (self.rsync_root, self.root)
        print(cmd)
        os.system(cmd)

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
        web.ctx.infobase_auth_token = None
        #@@ hack to disable permission check
        web.ctx.disable_permission_check = True
        site = self.infobase.get(entry.site)
        return getattr(self, entry.action)(site, entry.timestamp, entry.data)

    def write(self, site, timestamp, data):
        d = web.storage(data)
        author = d.author and site.withKey(d.author)
        return site.write(d.query, comment=d.comment, machine_comment=d.machine_comment, ip=d.ip, author=author, timestamp=timestamp)

    def save(self, site, timestamp, data):
        d = web.storage(data)
        author = d.author and site.withKey(d.author)
        return site.save(d.key, d.query, comment=d.comment, machine_comment=d.machine_comment, ip=d.ip, author=author, timestamp=timestamp)

    def new_account(self, site, timestamp, data):
        d = web.storage(data)
        a = site.get_account_manager()
        return a.register1(username=d.username, email=d.email, enc_password=d.password, data=dict(displayname=d.displayname), ip=d.ip, timestamp=timestamp)

    def update_account(self, site, timestamp, data):
        d = web.storage(data)
        user = site.withKey(d.username)
        a = site.get_account_manager()
        return a.update_user1(user,
            enc_password=d.get('password'),
            email=d.get('email'),
            ip = d.ip,
            timestamp=timestamp)

if __name__ == "__main__":
    import doctest
    doctest.testmod()

