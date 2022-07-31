from web.form import Button, Form, Textbox, net

from infogami.utils import i18n


class BetterButton(Button):
    def render(self):
        label = self.attrs.get('label', self.name)
        safename = net.websafe(self.name)
        x = f'<button name="{safename}"{self.addatts()}>{label}</button>'
        return x


_ = i18n.strings.get_namespace('/account/preferences')

template_preferences = Form(
    Textbox("path", description=_.template_root), BetterButton('save', label=_.save)
)

if __name__ == "__main__":
    print(template_preferences().render())
