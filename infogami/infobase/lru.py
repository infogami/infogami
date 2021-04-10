"""Infobase cache.
"""


class Node(object):
    """Queue Node."""

    __slots__ = ["key", "value", "next", "prev"]

    def __init__(self, key):
        self.key = key
        self.value = None
        self.next = None
        self.prev = None

    def __str__(self):
        return str(self.key)

    __repr__ = __str__


class Queue:
    """Classic Queue Datastructure with O(1) inserts and deletes.

    >>> q = Queue()
    >>> q
    []
    >>> a, b, c = Node(1), Node(2), Node(3)
    >>> q.insert(a)
    >>> q.insert(b)
    >>> q.insert(c)
    >>> q
    [1, 2, 3]
    >>> q.peek()
    1
    >>> q.remove(b)
    2
    >>> q
    [1, 3]
    >>> q.remove()
    1
    >>> q.remove()
    3
    >>> q.remove()
    Traceback (most recent call last):
        ...
    Exception: Queue is empty
    """

    def __init__(self):
        # circular linked-list implementation with
        # sentinel node to eliminate boundary checks
        head = self.head = Node("head")
        head.next = head.prev = head

    def clear(self):
        self.head.next = self.head.prev = self.head

    def insert(self, node):
        """Inserts a node at the end of the queue."""
        node.next = self.head
        node.prev = self.head.prev
        node.next.prev = node
        node.prev.next = node

    def peek(self):
        """Returns the element at the beginning of the queue."""
        if self.head.next is self.head:
            raise Exception("Queue is empty")
        return self.head.next

    def remove(self, node=None):
        """Removes a node from the linked list. If node is None, head of the queue is removed."""
        if node is None:
            node = self.peek()

        node.prev.next = node.next
        node.next.prev = node.prev
        return node

    def __str__(self):
        return str(list(self._list()))

    __repr__ = __str__

    def _list(self):
        node = self.head.next
        while node != self.head:
            yield node
            node = node.next


def synchronized(f):
    """Decorator to synchronize a method.
    Behavior of this is same as Java synchronized keyword.
    """

    def g(self, *a, **kw):
        # allocate the lock when the function is called for the first time.
        lock = getattr(self, '__lock__', None)
        if lock is None:
            import threading

            lock = threading.RLock()
            setattr(self, '__lock__', lock)

        try:
            lock.acquire()
            return f(self, *a, **kw)
        finally:
            lock.release()

    return g


class LRU:
    """Dictionary which discards least recently used items when size
    exceeds the specified capacity.

        >>> d = LRU(3)
        >>> d[1], d[2], d[3] = 1, 2, 3
        >>> d[1], d[2], d[3]
        (1, 2, 3)
        >>> d[2] and d
        [1, 3, 2]
        >>> d[1] and d
        [3, 2, 1]
        >>> d[4] = 4
        >>> d
        [2, 1, 4]
        >>> del d[1]
        >>> d
        [2, 4]
        >>> d[2] = 2
        >>> d
        [4, 2]
    """

    def __init__(self, capacity, d=None):
        self.capacity = capacity
        self.d = d or {}
        self.queue = Queue()

    @synchronized
    def getnode(self, key, touch=True):
        if key not in self.d:
            self.d[key] = Node(key)
        node = self.d[key]
        if touch:
            self.touch(node)
        return node

    @synchronized
    def touch(self, node):
        # don't call remove for newly created nodes
        node.next and self.queue.remove(node)
        self.queue.insert(node)

    @synchronized
    def prune(self):
        """Remove least recently used items if required."""
        while len(self.d) > self.capacity:
            self.remove_node()

    @synchronized
    def __contains__(self, key):
        return key in self.d

    @synchronized
    def __getitem__(self, key):
        node = self.d[key]
        self.touch(node)
        return node.value

    @synchronized
    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    @synchronized
    def __setitem__(self, key, value):
        self.getnode(key).value = value
        self.prune()

    @synchronized
    def __delitem__(self, key):
        if key not in self.d:
            raise KeyError(key)
        node = self.getnode(key, touch=False)
        self.remove_node(node)

    @synchronized
    def delete(self, key):
        try:
            del self[key]
        except KeyError:
            pass

    @synchronized
    def delete_many(self, keys):
        for k in keys:
            if k in self.d:
                del self[k]

    @synchronized
    def update(self, d):
        for k, v in d.items():
            self[k] = v

    @synchronized
    def keys(self):
        return list(self.d)

    @synchronized
    def items(self):
        return [(k, node.value) for k, node in self.d.items()]

    @synchronized
    def clear(self):
        self.d.clear()
        self.queue.clear()

    @synchronized
    def remove_node(self, node=None):
        node = self.queue.remove(node)
        del self.d[node.key]
        return node

    @synchronized
    def __str__(self):
        return str(self.queue)

    __repr__ = __str__


def lrumemoize(n):
    def decorator(f):
        cache = LRU(n)

        def g(*a, **kw):
            key = a, tuple(kw.items())
            if key not in cache:
                cache[key] = f(*a, **kw)
            return cache[key]

        return g

    return decorator


class ThingCache(LRU):
    """LRU Cache for storing things. Key can be either id or (site_id, key)."""

    def __init__(self, capacity):
        LRU.__init__(self, capacity)
        self.key2id = {}

    def __contains__(self, key):
        if isinstance(key, tuple):
            return key in self.key2id
        else:
            return LRU.__contains__(self, key)

    def __getitem__(self, key):
        if isinstance(key, tuple):
            key = self.key2id[key]
        return LRU.__getitem__(self, key)

    def get(self, key, default=None):
        if key in self:
            return self[key]
        else:
            return None

    def __setitem__(self, key, value):
        key = value.id
        LRU.__setitem__(self, key, value)
        # key2id mapping must be updated whenever a thing is added to the cache
        self.key2id[value._site.id, value.key] = value.id

    def __delitem__(self, key):
        if isinstance(key, tuple):
            key = self.key2id[key]
        return LRU.__delitem__(self, key)

    def remove_node(self, node=None):
        node = LRU.remove_node(self, node)
        thing = node.value
        # when a node is removed, its corresponding entry
        # from the key2id map must also be removed
        del self.key2id[thing._site.id, thing.key]
        return node

    def clear(self):
        LRU.clear(self)
        self.key2id.clear()


if __name__ == "__main__":
    import doctest

    doctest.testmod()
