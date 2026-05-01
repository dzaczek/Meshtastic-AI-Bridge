import os
import importlib
import pytest


def _load_app(tmp_path):
    os.environ['WEB_UI_PASSWORD'] = 'secret'
    os.environ['WEB_UI_USERNAME'] = 'admin'
    os.environ['WEB_UI_SECRET_KEY'] = 'test-secret-key'
    os.environ['WEB_UI_WEBAUTHN_RP_ID'] = 'localhost'
    os.environ['WEB_UI_WEBAUTHN_ORIGIN'] = 'http://localhost:8080'
    mod = importlib.import_module('web_ui')
    if not hasattr(mod, 'app'):
        pytest.skip('Flask/webauthn dependencies are not installed in this environment')
    mod._WEBAUTHN_CREDENTIALS_PATH = str(tmp_path / 'webauthn_credentials.json')
    mod.app.config['TESTING'] = True
    return mod.app


def test_passkey_login_begin_requires_configured_passkey(tmp_path):
    app = _load_app(tmp_path)
    c = app.test_client()
    r = c.post('/api/auth/passkey/login/begin', json={'username': 'admin'})
    assert r.status_code in (400, 501)
    assert r.get_json()['ok'] is False


def test_passkey_registration_requires_auth(tmp_path):
    app = _load_app(tmp_path)
    c = app.test_client()
    r = c.post('/api/auth/passkey/register/begin')
    assert r.status_code in (301, 302)
