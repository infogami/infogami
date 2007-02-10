from web.form import *
import db

login = Form(
    Textbox('username'),
    Password('password')
)

register = Form(
    Textbox('username', Validator(
             'Username already exists', 
             lambda name: not db.get_user_by_name(name))),
    Textbox('email'),
    Password('password')
)
