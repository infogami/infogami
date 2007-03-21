from web.form import *
import db
from infogami.utils import i18n

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
