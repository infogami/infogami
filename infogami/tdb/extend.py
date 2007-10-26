"""
Extend: Object inheritance system.

    >>> class A(Extend):
    ...     def foo(self): self.say('foo')
    ...     def say(self, msg): 
    ...         print 'a.say', msg
    ...
    >>> class B(Extend):
    ...     def say(self, msg): 
    ...         print 'b.say', msg
    ...         self.super_say('super ' + msg)    
    ...
    >>> class C(Extend):
    ...     def say(self, msg): 
    ...         print 'c.say', msg
    ...         self.super_say('super ' + msg)
    ...
    >>> a = A()
    >>> b = B()
    >>> c = C()
    >>> b.extend_from(a)
    >>> b.foo()
    b.say foo
    a.say super foo
    >>> c.extend_from(b)
    >>> c.foo()
    c.say foo
    b.say super foo
    a.say super super foo
    
Open Issues:
    * after b.extend_from(a), behavior of a also changes. Probably it should not.
    * semantics of __setattr__
"""

import types

class ExtendMetaClass(type):
    def __init__(cls, *a, **kw):
        keys = [k for k in cls.__dict__.keys() if not k.startswith('__')]
        d = [(k, getattr(cls, k)) for k in keys]
        for k in keys:
            delattr(cls, k)
            
        cls._d = dict(d)

        def curry(f, arg1):
            def g(*a, **kw):
                return f(arg1, *a, **kw)
            g.__name__ = f.__name__
            return g
                    
        def _getattr(self, name):
            """Get value of attribute from self or super."""
            if name in self.__dict__:
                return self.__dict__[name]
            elif name in self._d:
                value = self._d[name]
                if isinstance(value, types.MethodType):
                    return curry(value, self)
                else:
                    return value
            else:        
                if self._super != None:
                    return self._super._getattr(name)
                else:
                    raise AttributeError, name

        def __getattr__(self, name):
            """Returns value of the attribute from the sub object.
            If there is no sub object, self._getattr is called.
            """
            if name.startswith('super_'):
                return self._super._getattr(name[len('super_'):])
        
            if self._sub is not None:
                return getattr(self._sub, name)
            else:
                return self._getattr(name)
                    
        def extend_from(self, super):
            """Makes self extend from super.
            """
            self._super = super
            super._sub = self
                    
        cls.__getattr__ = __getattr__
        cls._getattr = _getattr
        cls._super = None
        cls._sub = None
        cls.extend_from = extend_from
        
class Extend:
    __metaclass__ = ExtendMetaClass
    def __init__(self, super=None):
        if super:
            self.extend_from(super)

if __name__ == "__main__":
    import doctest
    doctest.testmod()