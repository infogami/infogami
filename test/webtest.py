"""webtest: test utilities.
"""
import sys, os
import web

# adding current directory to path to make sure local copy of web module is used.
sys.path.insert(0, '.')

import unittest

TestCase = unittest.TestCase

def runTests(suite):
    runner = unittest.TextTestRunner()
    return runner.run(suite)
    
def main(suite=None):
    web.config.db_parameters = dict(dbn='postgres', db='infobase_test', user='scott', pw='tiger')
    web.load()
    
    if not suite:
        main_module = __import__('__main__')
        suite = module_suite(main_module, sys.argv[1:] or None)
        
    result = runTests(suite)
    sys.exit(not result.wasSuccessful())

def suite(module_names):
    """Creates a suite from multiple modules."""
    suite = unittest.TestSuite()
    for mod in load_modules(module_names):
        suite.addTest(module_suite(mod))
    return suite

def load_modules(names):
    return [__import__(name, None, None, "x") for name in names]

def module_suite(module, classnames=None):
    """Makes a suite from a module."""
    if hasattr(module, 'suite'):
        return module.suite()
    elif classnames:
        return unittest.TestLoader().loadTestsFromNames(classnames, module)
    else:
        return unittest.TestLoader().loadTestsFromModule(module)

def with_debug(f):
    """Decorator to enable debug prints."""
    def g(*a, **kw):
        db_printing = web.config.get('db_printing')
        web.config.db_printing = True
        
        try:
            return f(*a, **kw)
        finally:
            web.config.db_printing = db_printing
    return g
