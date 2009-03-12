import web
import doctest, unittest

def add_doctests(suite):
    """create one test_xx function in globals for each doctest in the given module.
    """
    suite = web.test.make_doctest_suite()

    add_test(make_suite(module))

def add_test(test):
    if isinstance(test, unittest.TestSuite):
        for t in test._tests:
            add_test(t)
    elif isinstance(test, unittest.TestCase):
        test_method = getattr(test, test._testMethodName)
        def do_test(test_method=test_method):
            test_method()
        name = "test_" + test.id().replace(".", "_")
        globals()[name] = do_test
    else:
        doom

modules = [
    "infogami.core.code",
    "infogami.core.helpers",
    "infogami.utils.app",
    "infogami.utils.i18n",
    "infogami.utils.storage",
    "infogami.infobase.common",
    "infogami.infobase.client",
    "infogami.infobase.dbstore",
    "infogami.infobase.lru",
    "infogami.infobase.readquery",
    "infogami.infobase.utils",
    "infogami.infobase.writequery",
]
suite = web.test.doctest_suite(modules)
add_test(suite)
