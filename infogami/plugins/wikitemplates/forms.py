from __future__ import print_function
import web
from web.form import *
from infogami.utils import i18n

class BetterButton(Button):
    def render(self):
        label = self.attrs.get('label', self.name)
        safename = net.websafe(self.name)
        x = '<button name="%s"%s>%s</button>' % (safename, self.addatts(), label)
        return x

_ = i18n.strings.get_namespace('/account/preferences')

template_preferences = Form(
    Textbox("path", description=_.template_root),
    BetterButton('save', label=_.save)
)

if __name__ == "__main__":
    print(template_preferences().render())
