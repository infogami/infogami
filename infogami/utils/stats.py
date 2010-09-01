"""Library to collect count and timings of various part of code.

Here is an example usage:

    stats.begin("memcache", method="get", key="foo")
    memcache_client.get("foo")
    stats.end()
"""
import web
import time
from context import context

def _get_stats():
    if "stats" not in web.ctx:
        context.stats = web.ctx.stats = []
    return web.ctx.stats
    
def begin(name, **kw):
    stats = _get_stats()
    stats.append(web.storage(name=name, data=kw, t_start=time.time()))
    
def end():
    stats = _get_stats()
    s = stats[-1]

    s.t_end = time.time()
    s.time = s.t_end - s.t_start
    
def stats_summary():
    d = web.storage()
    
    for s in web.ctx.stats:
        if s.name not in d:
            d[s.name] = web.storage(count=0, time=0.0)
        d[s.name].count += 1
        d[s.name].time += s.time
        
    return d
