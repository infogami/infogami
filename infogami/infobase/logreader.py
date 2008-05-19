"""
Log file reader.
"""
import _json as simplejson

def readlog(logfile):
    """Returns an iterator over all the elements of the given log file."""
    for line in open(logfile).xreadlines():
        yield simplejson.loads(line)
        
def taillog(logroot):
    """Returns an infinite stream over the log."""
    #@@ to be implemented.
    pass
    
if __name__ == "__main__":
    for entry in taillog('log'):
        print entry
