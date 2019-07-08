"""Library to collect count and timings of various part of code.

Here is an example usage:

    stats.begin("memcache", method="get", key="foo")
    memcache_client.get("foo")
    stats.end()

Currently this doesn't support nesting.    
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
    stats.append(web.storage(name=name, data=kw, t_start=time.time(), time=0.0))

def end(**kw):
    stats = _get_stats()
    s = stats[-1]

    s.data.update(kw)
    s.t_end = time.time()
    s.time = s.t_end - s.t_start

def stats_summary():
    d = web.storage()

    if not web.ctx.get("stats"):
        return d

    total_measured = 0.0

    for s in web.ctx.stats:
        if s.name not in d:
            d[s.name] = web.storage(count=0, time=0.0)
        d[s.name].count += 1
        d[s.name].time += s.time
        total_measured += s.time

    # consider the start time of first stat as start of the request
    total_time = time.time() - web.ctx.stats[0].t_start
    d['total'] = web.storage(count=0, time=total_time, unaccounted=total_time-total_measured)

    return d
