"""Serve index.html with a fake API backed by the real pet.py, for checking the
page on the desktop. Usage: python3 tools/mock_server.py [port] [--speed N] [--hatched]"""
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
import pet  # noqa: E402

args = sys.argv[1:]
port = int(args[0]) if args and args[0].isdigit() else 8765
speed = float(args[args.index("--speed") + 1]) if "--speed" in args else 1.0
s = pet.new_state("Ember")
if "--hatched" in args:
    pet.apply_elapsed(s, 300)
message = ""
last = time.time()


def state_json():
    global last
    t = time.time()
    pet.apply_elapsed(s, (t - last) * speed)
    last = t
    d = pet.public(s)
    d["message"] = message
    d["clock_ok"] = True
    return json.dumps(d).encode()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, body, ctype="application/json"):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        global message
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/":
            with open(os.path.join(ROOT, "index.html"), "rb") as f:
                return self.reply(f.read(), "text/html; charset=utf-8")
        if u.path == "/api/act":
            state_json()
            ok, message = pet.act(s, q.get("a", ""), q.get("won", 0))
        elif u.path == "/api/rename" and q.get("name"):
            s["name"] = q["name"][:16]
        elif u.path == "/api/new_egg" and q.get("confirm") == "yes":
            s.clear()
            s.update(pet.new_state("Ember"))
        elif u.path == "/api/debug":  # mock only: set stats for screenshots
            for k, v in q.items():
                s[k] = json.loads(v)
        elif u.path not in ("/api/state", "/api/sync"):
            self.send_response(404)
            self.end_headers()
            return
        self.reply(state_json())


print("mock BoardPet on http://127.0.0.1:%d (speed x%g)" % (port, speed))
ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
