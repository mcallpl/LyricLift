# ck1pw super-admin door for LyricLift (Flask). Open app -> door keeps the
# launchpad tile flow consistent; verifies the ck1pw token, then lands on /.
import os, base64, json, time, secrets
from urllib.parse import urlencode
from flask import redirect, request, make_response
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.exceptions import InvalidSignature

BASE = 'https://ck1pw.peoplestar.com'
APP  = 'lyriclift'
RET  = 'https://lyriclift.peoplestar.com/ck1pw/return'
_PUB = load_pem_public_key(open(os.path.join(os.path.dirname(__file__), 'ck1pw_public.pem'), 'rb').read())

def _b64u(s):
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))

def _verify(token):
    try:
        h, p, s = token.split('.')
    except (ValueError, AttributeError):
        return None
    try:
        _PUB.verify(_b64u(s), (h + '.' + p).encode(), padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature:
        return None
    try:
        c = json.loads(_b64u(p))
    except Exception:
        return None
    if c.get('iss') != 'ck1pw' or c.get('aud') != APP or c.get('role') != 'superadmin':
        return None
    if time.time() >= c.get('exp', 0):
        return None
    return c

def register_ck1pw(app):
    @app.route('/ck1pw/login')
    def ck1pw_login():
        state = secrets.token_hex(8)
        resp = make_response(redirect(BASE + '/authorize.php?' + urlencode(
            {'app_id': APP, 'redirect_uri': RET, 'state': state})))
        resp.set_cookie('ck1pw_state', state, httponly=True, secure=True, samesite='Lax')
        return resp

    @app.route('/ck1pw/return')
    def ck1pw_return():
        token = request.args.get('token')
        if not token:
            return ('<!doctype html><script>var h=location.hash.slice(1);'
                    'if(h)location.replace(location.pathname+"?"+h);</script>')
        if request.args.get('state') != request.cookies.get('ck1pw_state'):
            return ('ck1pw: bad state', 403)
        if not _verify(token):
            return ('ck1pw: invalid token', 403)
        from ck1pw.gate import grant
        resp = make_response(redirect('/'))   # open app: master-key entry grants the psgate cookie
        resp.delete_cookie('ck1pw_state')
        return grant(resp)

    @app.route('/ck1pw/logout')
    def ck1pw_logout():
        return redirect(BASE + '/logout.php?redirect_uri=/')
