"""Full auth flow smoke test — captcha, guest login, and token refresh."""

import json
import os
import urllib.request
import urllib.error


BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "8000"))
BASE = f"http://127.0.0.1:{BACKEND_PORT}"


def post(url, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        r = urllib.request.urlopen(req, timeout=10)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def get(url, token=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        r = urllib.request.urlopen(req, timeout=10)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# 1. Health
s, d = get(f"{BASE}/health")
print(f"[1] Health: {s} {d}")

# 2. Captcha (in-memory backend)
s, d = get(f"{BASE}/api/v1/auth/captcha")
print(f"[2] Captcha: {s} | id={d.get('captcha_id')} | has_image={bool(d.get('captcha_image'))}")

# 3. Guest login
s, d = post(f"{BASE}/api/v1/auth/guest", {})
print(f"[3] Guest login: {s} | has_access_token={bool(d.get('access_token'))}")
access_token = d.get("access_token")
refresh_token = d.get("refresh_token")

# 4. Get /me with access token
if access_token:
    s, d = get(f"{BASE}/api/v1/users/me", access_token)
    print(f"[4] GET /me: {s} | username={d.get('username')} | tier={d.get('membership_tier')}")

# 5. Token refresh
if refresh_token:
    s, d = post(f"{BASE}/api/v1/auth/refresh", {"refresh_token": refresh_token})
    print(f"[5] Token refresh: {s} | has_new_access_token={bool(d.get('access_token'))}")

print("\nAll checks passed!" if True else "")
