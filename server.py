"""Single-user LinkedIn publishing desk. Run on loopback only."""
import json
import os
import secrets
import sqlite3
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlencode, urlsplit, parse_qs
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
ORIGIN = 'http://127.0.0.1:8787'
REDIRECT = ORIGIN + '/callback'
if (ROOT / '.env').is_file():
    for line in (ROOT / '.env').read_text().splitlines():
        key, sep, value = line.partition('=')
        if sep and key.strip() in ('LINKEDIN_CLIENT_ID', 'LINKEDIN_CLIENT_SECRET'):
            os.environ.setdefault(key.strip(), value.strip())
CLIENT = os.getenv('LINKEDIN_CLIENT_ID')
SECRET = os.getenv('LINKEDIN_CLIENT_SECRET')
os.umask(0o077)
db = sqlite3.connect(ROOT / 'postroom.sqlite')
db.row_factory = sqlite3.Row
db.executescript("""
CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY, name TEXT, subject TEXT, token TEXT, expires REAL);
CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY, text TEXT, subject TEXT, "when" REAL, state TEXT);
UPDATE posts SET state='Check LinkedIn' WHERE state='Publishing';
""")
oauth = {}


def profile():
    return db.execute('SELECT * FROM account WHERE expires > ?', (time.time(),)).fetchone()


def linkedin(url, body=None, token=None, form=False):
    headers = {'Accept': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if body is not None:
        headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
        body = (urlencode(body) if form else json.dumps(body)).encode()
    with urlopen(Request(url, data=body, headers=headers), timeout=12) as response:
        return json.loads(response.read() or '{}')


def deliver(post_id, account, message):
    with db:
        db.execute("UPDATE posts SET state='Publishing' WHERE id=?", (post_id,))
    try:
        linkedin('https://api.linkedin.com/v2/ugcPosts', {
            'author': 'urn:li:person:' + account['subject'],
            'lifecycleState': 'PUBLISHED',
            'specificContent': {'com.linkedin.ugc.ShareContent': {
                'shareCommentary': {'text': message}, 'shareMediaCategory': 'NONE'
            }},
            'visibility': {'com.linkedin.ugc.MemberNetworkVisibility': 'PUBLIC'}
        }, token=account['token'])
        state = 'Published'
    except Exception:
        state = 'Check LinkedIn'
    with db:
        db.execute('UPDATE posts SET state=? WHERE id=?', (state, post_id))
    return state


def tick():
    account = profile()
    if account:
        for post in db.execute(
            """SELECT * FROM posts WHERE state='Scheduled' AND subject=? AND "when"<=? ORDER BY "when" """,
            (account['subject'], time.time())
        ).fetchall():
            deliver(post['id'], account, post['text'])


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def json_reply(self, data, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def redirect(self, url):
        self.send_response(303)
        self.send_header('Location', url)
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()

    def local_host(self):
        if self.headers.get('Host') == '127.0.0.1:8787':
            return True
        self.send_error(403)
        return False

    def do_HEAD(self):
        if self.local_host() and self.path in ('/', '/index.html', '/style.css', '/app.js'):
            super().do_HEAD()
        else:
            self.send_error(404)

    def do_GET(self):
        if not self.local_host():
            return
        route = urlsplit(self.path)
        if route.path == '/api/state':
            account = profile()
            return self.json_reply({
                'name': account['name'] if account else None,
                'configured': bool(CLIENT and SECRET),
                'posts': [dict(post) for post in db.execute(
                    """SELECT id,text,"when",state FROM posts WHERE subject=? ORDER BY "when" DESC LIMIT 50""",
                    (account['subject'],)
                )] if account else []
            })
        if route.path == '/auth' and CLIENT and SECRET:
            state = secrets.token_urlsafe(32)
            oauth.clear()
            oauth[state] = time.monotonic() + 600
            return self.redirect('https://www.linkedin.com/oauth/v2/authorization?' + urlencode({
                'response_type': 'code', 'client_id': CLIENT, 'redirect_uri': REDIRECT,
                'state': state, 'scope': 'openid profile w_member_social'
            }))
        if route.path == '/callback':
            query = parse_qs(route.query)
            expiry = oauth.pop(query.get('state', [''])[0], 0)
            message = 'Connection expired or was cancelled. Try connecting again.'
            if expiry > time.monotonic() and query.get('code'):
                try:
                    grant = linkedin('https://www.linkedin.com/oauth/v2/accessToken', {
                        'grant_type': 'authorization_code', 'code': query['code'][0],
                        'client_id': CLIENT, 'client_secret': SECRET, 'redirect_uri': REDIRECT
                    }, form=True)
                    member = linkedin('https://api.linkedin.com/v2/userinfo', token=grant['access_token'])
                    with db:
                        db.execute('INSERT OR REPLACE INTO account VALUES (1,?,?,?,?)', (
                            member.get('name') or 'LinkedIn member', member['sub'], grant['access_token'],
                            time.time() + int(grant['expires_in'])
                        ))
                    message = 'LinkedIn connected.'
                except Exception:
                    message = 'LinkedIn could not connect. Check your app products, credentials, and callback URL.'
            return self.redirect('/?' + urlencode({'status': message}))
        if route.path in ('/', '/index.html', '/style.css', '/app.js'):
            return super().do_GET()
        self.send_error(404)

    def do_POST(self):
        if not self.local_host():
            return
        if self.headers.get('Origin') != ORIGIN or self.headers.get_content_type() != 'application/json':
            return self.json_reply({'error': 'Open Postroom from its local address.'}, 403)
        account = profile()
        if not account:
            return self.json_reply({'error': 'Connect LinkedIn first.'}, 409)
        try:
            size = int(self.headers['Content-Length'])
            if not 0 < size <= 32000:
                raise ValueError
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError
        except (TypeError, ValueError):
            return self.json_reply({'error': 'Invalid request.'}, 400)
        if self.path == '/api/disconnect':
            with db:
                db.execute('DELETE FROM account')
                db.execute("UPDATE posts SET state='Cancelled' WHERE subject=? AND state='Scheduled'", (account['subject'],))
            return self.json_reply({'message': 'Disconnected. Pending posts were cancelled.'})
        if self.path == '/api/cancel':
            with db:
                changed = db.execute("UPDATE posts SET state='Cancelled' WHERE id=? AND subject=? AND state='Scheduled'",
                                     (data.get('id') if isinstance(data.get('id'), int) else None, account['subject'])).rowcount
            return self.json_reply({'message': 'Post cancelled.'} if changed else {'error': 'Post is no longer scheduled.'}, 200 if changed else 409)
        if self.path not in ('/api/publish', '/api/schedule'):
            return self.json_reply({'error': 'Unknown action.'}, 404)
        message = data.get('text')
        if not isinstance(message, str) or not message.strip() or len(message) > 3000:
            return self.json_reply({'error': 'Enter up to 3,000 characters.'}, 400)
        scheduled = self.path == '/api/schedule'
        when = data.get('when') if scheduled else time.time()
        if scheduled and (type(when) not in (int, float) or not time.time() < when < account['expires']):
            return self.json_reply({'error': 'Choose a future time before your LinkedIn connection expires.'}, 400)
        with db:
            post_id = db.execute('INSERT INTO posts (text,subject,"when",state) VALUES (?,?,?,?)',
                                 (message.strip(), account['subject'], when, 'Scheduled' if scheduled else 'Publishing')).lastrowid
        if scheduled:
            return self.json_reply({'message': 'Post scheduled.'})
        if deliver(post_id, account, message.strip()) == 'Published':
            return self.json_reply({'message': 'Published to LinkedIn.'})
        return self.json_reply({'error': 'Could not confirm publication. Check LinkedIn before retrying.'}, 502)


if __name__ == '__main__':
    with HTTPServer(('127.0.0.1', 8787), partial(Handler, directory=ROOT)) as server:
        server.timeout = 2
        print('Postroom is running at ' + ORIGIN, flush=True)
        while True:
            server.handle_request()
            tick()
