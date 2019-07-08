"""Maintains a registry of path pattern vs type names to guess type from path when a page is newly created.
"""
import re
import storage

default_type = '/type/page'
type_patterns = storage.OrderedDict()

def register_type(pattern, typename):
    type_patterns[pattern] = typename

def guess_type(path):
    import web
    for pattern, typename in type_patterns.items():
        if re.search(pattern, path):
            return typename

    return default_type
