collect_ignore = ['failing']


def pytest_addoption(parser):
    parser.addoption("--runall", action="store_true", default=False)


def pytest_configure(config):
    if config.getvalue("runall"):
        collect_ignore[:] = []
