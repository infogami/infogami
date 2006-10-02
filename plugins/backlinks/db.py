class SQL:
    def new_link(self, site, tail_path, head_path):
        site = db.get_site(site)
        web.insert('backlinks_link', False,
          tail=db.get_page(site, tail_path), head_site=site, head_path=head_path)
    
    def get_links(self, site, tail_path):
        tail = db.get_page(site, tail_path).id
        return web.select('backlinks_link', where="tail = $tail", vars=locals())
