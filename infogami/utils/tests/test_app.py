from infogami.utils import app

def test_parse_accept():

    # testing examples from http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html
    assert app.parse_accept("audio/*; q=0.2, audio/basic") == [
        {"media_type": "audio/basic"},
        {"media_type": "audio/*", "q": 0.2}
    ]

    assert app.parse_accept("text/plain; q=0.5, text/html, text/x-dvi; q=0.8, text/x-c") == [
        {"media_type": "text/html"},
        {"media_type": "text/x-c"},
        {"media_type": "text/x-dvi", "q": 0.8},
        {"media_type": "text/plain", "q": 0.5}
    ]

    # try empty
    assert app.parse_accept("") == [
        {'media_type': ''}
    ]
    assert app.parse_accept(" ") == [
        {'media_type': ''}
    ]
    assert app.parse_accept(",") == [
        {'media_type': ''},
        {'media_type': ''}
    ]

    # try some bad ones
    assert app.parse_accept("hc/url;*/*") == [
        {"media_type": "hc/url"}
    ]
    assert app.parse_accept("text/plain;q=bad") == [
        {"media_type": "text/plain"}
    ]

    assert app.parse_accept(";q=1") == [
        {"media_type": "", "q": 1.0}
    ]
