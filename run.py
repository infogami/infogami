#!/usr/bin/python
import web

if __name__ == "__main__":
    from utils import delegate
    delegate._load()
    web.run(delegate.urls, delegate.__dict__)
