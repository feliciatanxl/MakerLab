"""Get a Spotify refresh token and save it to arduino_secrets.h.

This script runs only on your computer. It never prints your client secret,
authorization code, or refresh token.
"""

from __future__ import annotations

import base64
import json
import re
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


SKETCH_DIR = Path(__file__).resolve().parent
SECRETS_FILE = SKETCH_DIR / "arduino_secrets.h"
REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPE = "user-read-currently-playing"


def read_define(source: str, name: str) -> str:
    pattern = re.compile(
        rf'^\s*#define\s+{re.escape(name)}\s+"([^"\r\n]*)"', re.MULTILINE
    )
    match = pattern.search(source)
    if not match:
        raise RuntimeError(f"{name} is missing from arduino_secrets.h")
    value = match.group(1).strip()
    if not value or value.startswith("your_"):
        raise RuntimeError(f"Fill in {name} in arduino_secrets.h first")
    return value


def save_refresh_token(source: str, token: str) -> None:
    pattern = re.compile(
        r'(^\s*#define\s+SECRET_SPOTIFY_REFRESH_TOKEN\s+")([^"\r\n]*)(".*$)',
        re.MULTILINE,
    )
    if not pattern.search(source):
        raise RuntimeError(
            "SECRET_SPOTIFY_REFRESH_TOKEN is missing from arduino_secrets.h"
        )
    updated = pattern.sub(lambda match: match.group(1) + token + match.group(3), source, count=1)
    SECRETS_FILE.write_text(updated, encoding="utf-8")


class CallbackHandler(BaseHTTPRequestHandler):
    query: dict[str, list[str]] | None = None

    def do_GET(self) -> None:  # noqa: N802 - method name comes from BaseHTTPRequestHandler
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_error(404)
            return

        type(self).query = urllib.parse.parse_qs(parsed.query)
        page = (
            "<html><body style='font-family:sans-serif'>"
            "<h2>Spotify authorization received</h2>"
            "<p>You can close this tab and return to the command window.</p>"
            "</body></html>"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def exchange_code(client_id: str, client_secret: str, code: str) -> str:
    form = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        }
    ).encode("ascii")
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode(
        "ascii"
    )
    request = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=form,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            detail = payload.get("error_description") or payload.get("error")
        except (UnicodeDecodeError, json.JSONDecodeError):
            detail = f"HTTP {exc.code}"
        raise RuntimeError(f"Spotify rejected the token exchange: {detail}") from exc

    token = payload.get("refresh_token")
    if not token:
        raise RuntimeError("Spotify did not return a refresh token")
    return token


def main() -> int:
    if not SECRETS_FILE.exists():
        raise RuntimeError(
            "arduino_secrets.h is missing. Copy arduino_secrets.example.h first."
        )

    source = SECRETS_FILE.read_text(encoding="utf-8")
    client_id = read_define(source, "SECRET_SPOTIFY_CLIENT_ID")
    client_secret = read_define(source, "SECRET_SPOTIFY_CLIENT_SECRET")

    state = secrets.token_urlsafe(24)
    authorize_url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPE,
            "state": state,
            "show_dialog": "true",
        }
    )

    try:
        server = HTTPServer(("127.0.0.1", 8888), CallbackHandler)
    except OSError as exc:
        raise RuntimeError(
            "Cannot use local port 8888. Close any program using it and try again."
        ) from exc

    server.timeout = 300
    print("Opening Spotify in your browser...")
    print("Approve access, then return here. This window waits up to 5 minutes.")
    if not webbrowser.open(authorize_url):
        print("Your browser did not open. Paste this address into a browser:")
        print(authorize_url)

    server.handle_request()
    server.server_close()

    query = CallbackHandler.query
    if query is None:
        raise RuntimeError("Timed out waiting for Spotify authorization")
    if query.get("state", [""])[0] != state:
        raise RuntimeError("Spotify callback state did not match; please try again")
    if "error" in query:
        raise RuntimeError(f"Spotify authorization failed: {query['error'][0]}")

    code = query.get("code", [""])[0]
    if not code:
        raise RuntimeError("Spotify callback did not contain an authorization code")

    refresh_token = exchange_code(client_id, client_secret, code)
    save_refresh_token(source, refresh_token)
    print("Success: the refresh token was saved in arduino_secrets.h.")
    print("Return to Arduino IDE and upload Spotify.ino again.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
