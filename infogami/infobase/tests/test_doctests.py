import doctest
import pytest

modules = [
    "infogami.infobase.account",
    "infogami.infobase.bootstrap",
    "infogami.infobase.cache",
    "infogami.infobase.client",
    "infogami.infobase.common",
    "infogami.infobase.core",
    "infogami.infobase.dbstore",
    "infogami.infobase.infobase",
    "infogami.infobase.logger",
    "infogami.infobase.logreader",
    "infogami.infobase.lru",
    "infogami.infobase.readquery",
    "infogami.infobase.tests.pytest_wildcard",
    "infogami.infobase.utils",
    "infogami.infobase.writequery",
]


@pytest.mark.parametrize('module', modules)
def test_doctest(module):
    mod = __import__(module, None, None, ['x'])
    finder = doctest.DocTestFinder()
    tests = finder.find(mod, mod.__name__)
    for test in tests:
        runner = doctest.DocTestRunner(verbose=True)
        failures, tries = runner.run(test)
        if failures:
            pytest.fail("doctest failed: " + test.name)
