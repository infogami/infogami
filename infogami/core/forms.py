from web.form import *
import db
from infogami.utils import i18n
from infogami.utils.context import context

_ = i18n.i18n()

login = Form(
    Hidden('redirect'),
    Textbox('username', description=_.USERNAME),
    Password('password', description=_.PASSWORD),
    Checkbox('remember', description=_.REMEMBER_ME)
)

vlogin = regexp(r"^[A-Za-z0-9-_]{3,20}$", 'must be between 3 and 20 letters and numbers') 
vpass = regexp(r".{3,20}", 'must be between 3 and 20 characters')

register = Form(
    Textbox('username', 
            Validator(
                _.USERNAME_ALREADY_EXISTS,
                lambda name: not db.get_user_by_name(context.site, name)),
            vlogin,
            description=_.USERNAME),
    Textbox('displayname', notnull, description=_.DISPLAYNAME),
    Textbox('email', notnull, description=_.EMAIL),
    Password('password', notnull, vpass, description=_.PASSWORD),
    Password('password2', notnull, description=_.CONFIRM_PASSWORD),
    validators = [
        Validator(_.PASSWORDS_DID_NOT_MATCH, lambda i: i.password == i.password2)]    
)

login_preferences = Form(
    Password("oldpassword", notnull, description=_.CURRENT_PASSWORD),
    Password("password", notnull, vpass, description=_.NEW_PASSWORD),
    Password("password2", notnull, description=_.CONFIRM_PASSWORD),
    Button("Save"),
    validators = [
        Validator(_.INCORRECT_PASSWORD, lambda i: auth.check_password(context.user, i.oldpassword)),
        Validator(_.PASSWORDS_DID_NOT_MATCH, lambda i: i.password == i.password2)]
)
