"""psgate — simple-password gate for LyricLift (mirrors the shared PHP gate).

One password, one-year HMAC-signed cookie; secret shared with the other apps
at /etc/ck1pw/gate.secret. The ck1pw master-key door stays exempt, and a
successful master-key return also grants the gate cookie (see door.py).
"""
import hashlib
import hmac
import time

from flask import make_response, redirect, request

COOKIE = 'psgate'
TTL = 31536000  # 1 year
SECRET_FILE = '/etc/ck1pw/gate.secret'
PASSWORD = 'amazing'

_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LyricLift &mdash; Private</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
         background:#0f172a; color:#e8eaf2; min-height:100vh;
         display:flex; align-items:center; justify-content:center; padding:20px; }}
  .card {{ width:100%; max-width:340px; background:#1a2440; border:1px solid #2b3a5e;
          border-radius:16px; padding:36px 28px; text-align:center; }}
  .lock {{ font-size:2rem; }}
  h1 {{ font-size:1.15rem; margin:12px 0 4px; font-weight:700; }}
  p  {{ color:#8b93a7; font-size:.85rem; margin-bottom:22px; }}
  input {{ width:100%; padding:13px 14px; border-radius:10px; border:1px solid #2b3a5e;
          background:#0f172a; color:#e8eaf2; font-size:1rem; outline:none; }}
  input:focus {{ border-color:#3b82f6; }}
  button {{ width:100%; margin-top:12px; padding:13px; border:0; border-radius:10px;
           background:#2563eb; color:#fff; font-size:1rem; font-weight:600; cursor:pointer; }}
  .err {{ color:#f87171; font-size:.85rem; margin-top:12px; {err_css} }}
</style>
</head>
<body>
  <form class="card" method="post" action="/__gate/">
    <div class="lock">&#128274;</div>
    <h1>LyricLift</h1>
    <p>This app is private. Enter the password to continue.</p>
    <input type="password" name="password" placeholder="Password" autofocus autocomplete="current-password">
    <input type="hidden" name="next" value="{next}">
    <button type="submit">Unlock</button>
    <div class="err">Wrong password &mdash; try again.</div>
  </form>
</body>
</html>"""


def _secret():
    with open(SECRET_FILE) as f:
        return f.read().strip()


def _sign(exp):
    mac = hmac.new(_secret().encode(), f'psgate|{exp}'.encode(), hashlib.sha256)
    return f'{exp}.{mac.hexdigest()}'


def _valid():
    v = request.cookies.get(COOKIE, '')
    exp_s, _, _sig = v.partition('.')
    if not exp_s.isdigit():
        return False
    exp = int(exp_s)
    if exp < time.time():
        return False
    return hmac.compare_digest(_sign(exp), v)


def grant(resp):
    """Set the one-year gate cookie on a response (also used by the ck1pw door)."""
    resp.set_cookie(COOKIE, _sign(int(time.time()) + TTL), max_age=TTL,
                    secure=True, httponly=True, samesite='Lax')
    return resp


def _safe_next(raw):
    return raw if raw.startswith('/') and not raw.startswith('//') else '/'


def _page(next_path, error=False):
    html = _PAGE.format(err_css='' if error else 'display:none;',
                        next=next_path.replace('"', ''))
    return html


def register_gate(app):
    @app.route('/__gate/', methods=['GET', 'POST'])
    def psgate():
        if request.method == 'POST':
            nxt = _safe_next(request.form.get('next', '/'))
            if hmac.compare_digest(request.form.get('password', ''), PASSWORD):
                return grant(make_response(redirect(nxt)))
            time.sleep(1)  # slow brute force
            return _page(nxt, error=True), 401
        return _page(_safe_next(request.args.get('next', '/')))

    @app.before_request
    def psgate_check():
        p = request.path
        if p.startswith('/__gate') or p.startswith('/ck1pw'):
            return None
        if _valid():
            return None
        if request.method == 'GET':
            return redirect('/__gate/?next=' + p)
        return ('gate: not authorized', 401)
