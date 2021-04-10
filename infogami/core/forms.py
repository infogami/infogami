from web.form import (
    Button,
    Checkbox,
    Form,
    Hidden,
    Password,
    Textbox,
    Validator,
    net,
    notnull,
    regexp,
)
from web.form import *  # noqa: F40 TODO (cclauss): Remove wildcard imports


from infogami.core import db
from infogami.utils import i18n
from infogami.utils.context import context


class BetterButton(Button):
    def render(self):
        label = self.attrs.get('label', self.name)
        safename = net.websafe(self.name)
        x = '<button name="%s"%s>%s</button>' % (safename, self.addatts(), label)
        return x


_ = i18n.strings.get_namespace('/account/login')

login = Form(
    Hidden('redirect'),
    Textbox('username', notnull, description=_.username),
    Password('password', notnull, description=_.password),
    Checkbox('remember', description=_.remember_me),
)

vlogin = regexp(
    r"^[A-Za-z0-9-_]{3,20}$", 'must be between 3 and 20 letters and numbers'
)
vpass = regexp(r".{3,20}", 'must be between 3 and 20 characters')
vemail = regexp(r".*@.*", "must be a valid email address")
not_already_used = Validator(
    'This email is already used',
    lambda email: db.get_user_by_email(context.site, email) is None,
)

_ = i18n.strings.get_namespace('/account/register')

register = Form(
    Textbox('username', vlogin, description=_.username),
    Textbox('displayname', notnull, description=_.display_name),
    Textbox('email', notnull, vemail, description=_.email),
    Password('password', notnull, vpass, description=_.password),
    Password('password2', notnull, description=_.confirm_password),
    validators=[
        Validator(_.passwords_did_not_match, lambda i: i.password == i.password2)
    ],
)

_ = i18n.strings.get_namespace('/account/preferences')

login_preferences = Form(
    Password("oldpassword", notnull, description=_.current_password),
    Password("password", notnull, vpass, description=_.new_password),
    Password("password2", notnull, description=_.confirm_password),
    BetterButton("save", label=_.save),
    validators=[
        Validator(_.passwords_did_not_match, lambda i: i.password == i.password2)
    ],
)

_ = i18n.strings.get_namespace('/account/forgot_password')

validemail = Validator(
    _.email_not_registered, lambda email: db.get_user_by_email(context.site, email)
)
forgot_password = Form(
    Textbox('email', notnull, vemail, description=_.email),
)

_register = i18n.strings.get_namespace('/account/register')
_preferences = i18n.strings.get_namespace('/account/preferences')

reset_password = Form(
    Password('password', notnull, vpass, description=_register.password),
    Password('password2', notnull, description=_register.confirm_password),
    BetterButton("save", label=_preferences.save),
    validators=[
        Validator(
            _register.passwords_did_not_match, lambda i: i.password == i.password2
        )
    ],
)
