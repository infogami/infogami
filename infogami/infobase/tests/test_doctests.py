import doctest
import py.test

def test_doctest():
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
        "infogami.infobase.utils",
        "infogami.infobase.writequery",
    ]
    for test in find_doctests(modules):
        yield run_doctest, test

def find_doctests(modules):
    finder = doctest.DocTestFinder()
    for m in modules:
        mod = __import__(m, None, None, ['x'])
        for t in finder.find(mod, mod.__name__):
            yield t

def run_doctest(test):
    runner = doctest.DocTestRunner(verbose=True)
    failures, tries = runner.run(test)
    if failures:
        py.test.fail("doctest failed: " + test.name)
