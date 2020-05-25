import web
from difflib import SequenceMatcher

def better_diff(a, b):
    labels = dict(equal="", insert='add', replace='mod', delete='rem')

    map = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(a=a, b=b).get_opcodes():
        n = (j2-j1) - (i2-i1)

        x = a[i1:i2]
        xn = list(range(i1, i2))
        y = b[j1:j2]
        yn = list(range(j1, j2))

        if tag == 'insert':
            x += [''] * n
            xn += [''] * n
        elif tag == 'delete':
            y += [''] * -n
            yn += [''] * -n
        elif tag == 'equal':
            if i2-i1 > 5:
                x = y = [a[i1], '', a[i2-1]]
                xn = yn = [i1, '...', i2-1]
        elif tag == 'replace':
            isize = i2-i1
            jsize = j2-j1

            if isize < jsize:
                x += [''] * (jsize-isize)
                xn += [''] * (jsize-isize)
            else:
                y += [''] * (isize-jsize)
                yn += [''] * (isize-jsize)

        map += zip([labels[tag]] * len(x), xn, x, yn, y)

    return map

def simple_diff(a, b):
    a = a or ''
    b = b or ''
    if a is None: a = ''
    if b is None: b = ''
    a = web.utf8(a).split(' ')
    b = web.utf8(b).split(' ')
    out = []
    for (tag, i1, i2, j1, j2) in SequenceMatcher(a=a, b=b).get_opcodes():
        out.append(web.storage(tag=tag, left=' '.join(a[i1:i2]), right=' '.join(b[j1:j2])))
    return out
