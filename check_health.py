import urllib.request
import json

# Test backend health
try:
    r = urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5)
    print("BACKEND HEALTH:", r.read().decode())
except Exception as e:
    print("BACKEND HEALTH FAILED:", e)

# Test captcha endpoint
try:
    r = urllib.request.urlopen("http://127.0.0.1:8000/api/v1/auth/captcha", timeout=5)
    data = json.loads(r.read())
    print("CAPTCHA OK - id:", data.get("captcha_id"), "| has_image:", bool(data.get("captcha_image")))
except Exception as e:
    print("CAPTCHA FAILED:", e)

# Test frontend
try:
    r = urllib.request.urlopen("http://localhost:5173/", timeout=5)
    body = r.read().decode()
    has_app = "app" in body
    print("FRONTEND status:", r.status, "| has app:", has_app)
except Exception as e:
    print("FRONTEND FAILED:", e)
