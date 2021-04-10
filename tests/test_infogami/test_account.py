from infogami.utils.delegate import app
import pytest
import web

b = app.browser()


@pytest.mark.skip(
    reason="Browser test not currently functioning, requires BeautifulSoup and ClientForm, and site is still set to None"
)
def test_login():
    # try with bad account
    b.open('/account/login')
    b.select_form(name='login')
    b['username'] = 'joe'
    b['password'] = 'secret'

    try:
        b.submit()
    except web.BrowserError as e:
        assert str(e) == 'Invalid username or password'
    else:
        assert False, 'Expected exception'

    # follow register link
    b.follow_link(text='create a new account')
    assert b.path == '/account/register'

    b.select_form('register')
    b['username'] = 'joe'
    b['displayname'] = 'Joe'
    b['password'] = 'secret'
    b['password2'] = 'secret'
    b['email'] = 'joe@example.com'
    b.submit()
    assert b.path == '/'
