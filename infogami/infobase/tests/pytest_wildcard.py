"""py.test wildcard plugin.
"""

import pytest

class Wildcard:
    """Wildcard object is equal to anything.

    Useful to compare datastructures which contain some random numbers or db sequences.

        >>> import random
        >>> asseert [random.random(), 1, 2] == [wildcard, 1, 2]
    """
    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return False

    def __repr__(self):
        return '<?>'

wildcard = Wildcard()

def test_wildcard():
    assert wildcard == 1
    assert wildcard == [1, 2, 3]
    assert 1 == wildcard
    assert ["foo", 1, 2] == [wildcard, 1, 2]

@pytest.fixture
def wildcard(request):
    """Returns the wildcard object.

    Wildcard object is equal to anything. It is useful in testing datastuctures with some random parts. 

        >>> import random
        >>> asseert [random.random(), 1, 2] == [wildcard, 1, 2]
    """
    return wildcard
