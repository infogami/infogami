from web.form import *
import db, auth
from infogami.utils import i18n
from infogami.utils.context import context

class BetterButton(Button):
    def render(self):
        label = self.attrs.get('label', self.name)
        safename = net.websafe(self.name)
        x = '<button name="%s"%s>%s</button>' % (safename, self.addatts(), label)
        return x

_ = i18n.strings

login = Form(
    Hidden('redirect'),
    Textbox('username', notnull, description=_.get("account/login", "username")),
    Password('password', notnull, description=_.get("account/login", "password")),
    Checkbox('remember', description=_.get("account/login", "remember_me"))
)

vlogin = regexp(r"^[A-Za-z0-9-_]{3,20}$", 'must be between 3 and 20 letters and numbers') 
vpass = regexp(r".{3,20}", 'must be between 3 and 20 characters')
vemail = regexp(r".*@.*", "must be a valid email address")
not_already_used = Validator('This email is already used', lambda email: db.get_user_by_email(context.site, email) is None)

register = Form(
    Textbox('username', 
            vlogin,
            description=_.get('account/register', 'username')),
    Textbox('displayname', notnull, description=_.get('account/register', 'display_name')),
    Textbox('email', notnull, vemail, description=_.get('account/register', 'email')),
    Password('password', notnull, vpass, description=_.get('account/register', 'password')),
    Password('password2', notnull, description=_.get('account/register', 'confirm_password')),
    validators = [
        Validator(_.get('account/register', 'passwords_did_not_match'), lambda i: i.password == i.password2)]    
)

login_preferences = Form(
    Password("oldpassword", notnull, description=_.get("account/preferences", "current_password")),
    Password("password", notnull, vpass, description=_.get("account/preferences", "new_password")),
    Password("password2", notnull, description=_.get("account/preferences", "confirm_password")),
    BetterButton("save", label=_.get('account/preferences', 'save')),
    validators = [
        Validator(_.get("account/preferences", "incorrect_password"), lambda i: auth.check_password(context.user, i.oldpassword)),
        Validator(_.get("account/preferences", "passwords_did_not_match"), lambda i: i.password == i.password2)]
)

validemail = Validator(_.get("account/forgot_password", "email_not_registered"), 
                        lambda email: db.get_user_by_email(context.site, email))
forgot_password = Form(
    Textbox('email', notnull, vemail, validemail, description=_.get("account/forgot_password", "email")),
)
