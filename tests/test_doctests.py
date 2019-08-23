import unittest
from web.test import doctest_suite


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

suite = doctest_suite(modules)

add_test(suite)
