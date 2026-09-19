"""Smoke HTTP: pega a los endpoints reales y vuelca a e2e_out.json."""
import json, sys, urllib.request, urllib.parse, urllib.error

BASE = "http://127.0.0.1:8765"

def get(path, headers=None, timeout=10):
    req = urllib.request.Request(BASE + path, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return {"status": r.status, "headers": dict(r.headers), "body": r.read().decode("utf-8")}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "headers": dict(e.headers), "body": ""}
    except Exception as e:
        return {"status": 0, "error": repr(e), "body": ""}

opts = [
    ("GET", "/"),
    ("GET", "/api/health"),
    ("GET", "/api/sorteos"),
    ("GET", "/api/estadisticas"),
    ("GET", "/api/suenos?" + urllib.parse.urlencode({"texto": "soñe con un gato negro y dinero"})),
    ("GET", "/api/suenos?" + urllib.parse.urlencode({"texto": "krypton volando con ballenas"})),
    ("GET", "/api/suenos"),  # sin texto → debería 400
]
out = {}
for method, p in opts:
    r = get(p)
    out[p] = {"status": r["status"], "cors_acao": r["headers"].get("access-control-allow-origin"),
              "len": len(r["body"]), "body_sample": r["body"][:240]}

# Explicito CORS: preflight-like
cors = get("/api/sorteos", headers={
    "Origin": "https://quiniela-tucuman.vercel.app",
    "Access-Control-Request-Method": "GET",
})
out["__CORS_VERIFICADO__"] = {"acao": cors["headers"].get("access-control-allow-origin"),
                              "acam": cors["headers"].get("access-control-allow-methods"),
                              "acah": cors["headers"].get("access-control-allow-headers")}

with open("e2e_out.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("ENDPOINTS OK", file=sys.stderr)
