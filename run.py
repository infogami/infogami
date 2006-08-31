import web

if __name__ == "__main__":
    from utils import delegate
    web.run(delegate.urls, delegate.__dict__)
