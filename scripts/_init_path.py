"""Utility to setup sys.path.
"""

from os.path import abspath, dirname, pardir, join
import sys

INFOGAMI_PATH = abspath(join(dirname(__file__), pardir))
sys.path.insert(0, INFOGAMI_PATH)

