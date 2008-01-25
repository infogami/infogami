import web
from web.form import *
from infogami.utils.i18n import strings as _

class BetterButton(Button):
    def render(self):
        label = self.attrs.get('label', self.name)
        safename = net.websafe(self.name)
        x = '<button name="%s"%s>%s</button>' % (safename, self.addatts(), label)
        return x
    
template_preferences = Form(
    Textbox("path", description=_.get('account/preferences', 'template_root')),
    BetterButton('save', label=_.get('account/preferences', 'save'))
)

if __name__ == "__main__":
    print template_preferences().render()