from web.form import *
import db
from infogami.utils import i18n
from infogami.utils.context import context

_ = i18n.i18n()

login = Form(
    Textbox('username', description=_.USERNAME),
    Password('password', description=_.PASSWORD),
    Checkbox('remember', description=_.REMEMBER_ME)
)

register = Form(
    Textbox('username', 
            Validator(
                'Username already exists', 
                lambda name: not db.get_user_by_name(name)),
            description=_.USERNAME),
    Textbox('email', description=_.EMAIL),
    Password('password', description=_.PASSWORD)
)

login_preferences = Form(
    Password("oldpassword", notnull, description="Current Password"),
    Password("password", notnull, description="New Password"),
    Password("password2", notnull, description="Re-enter Password"),
    Button("Save"),
    validators = [
        Validator("Incorrect password.", lambda i: i.oldpassword == context.user.password),
        Validator("Passwords didn't match.", lambda i: i.password == i.password2)]
)
