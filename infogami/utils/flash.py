"""Utility to display flash messages.

To add a flash message:

    add_flash_message('info', 'Login successful!')

To display flash messages in a template:

    $ for flash in get_flash_messages():
        <div class="$flash.type">$flash.message</div>
"""

import simplejson
import web

def get_flash_messages():
    flash = web.ctx.get('flash', [])
    web.ctx.flash = []
    return flash

def add_flash_message(type, message):
    flash = web.ctx.setdefault('flash', [])
    flash.append(web.storage(type=type, message=message))

def flash_processor(handler):
    flash = web.cookies(flash="[]").flash
    try:
        flash = [web.storage(d) for d in simplejson.loads(flash) if isinstance(d, dict) and 'type' in d and 'message' in d]
    except ValueError:
        flash = []

    web.ctx.flash = list(flash)

    try:
        return handler()
    finally:
        # Flash changed. Need to save it.
        if flash != web.ctx.flash:
            if web.ctx.flash:
                web.setcookie('flash', simplejson.dumps(web.ctx.flash))
            else:
                web.setcookie('flash', '', expires=-1)
