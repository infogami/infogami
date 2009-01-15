"""Run all doctests in infogami.
"""
import webtest

def suite():
    modules = [
        "infogami.infobase.common",
        "infogami.infobase.readquery",
        "infogami.infobase.writequery",
        "infogami.infobase.dbstore",
    ]
    return webtest.doctest_suite(modules)
    
if __name__ == "__main__":
    webtest.main()
