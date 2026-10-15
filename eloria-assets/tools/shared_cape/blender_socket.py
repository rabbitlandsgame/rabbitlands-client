"""Send Python to the live Blender MCP add-on (localhost:9876). usage: python blx.py file.py | python blx.py -c 'code'"""
import json, os, socket, sys
code = sys.argv[2] if sys.argv[1] == "-c" else open(sys.argv[1], encoding="utf-8").read()
here = os.path.dirname(os.path.abspath(__file__)).replace(chr(92), "/")
code = "SCR = " + repr(here) + chr(10) + code
req = json.dumps({"type": "execute", "code": code, "strict_json": False}) + chr(0)
with socket.socket() as s:
    s.settimeout(1800)
    s.connect(("localhost", 9876))
    s.sendall(req.encode())
    buf = bytearray()
    while b"\0" not in buf:
        c = s.recv(65536)
        if not c:
            break
        buf.extend(c)
r = json.loads(buf.partition(b"\0")[0].decode())
for k in ("stdout", "stderr"):
    if r.get(k):
        lines = [l for l in r[k].splitlines() if "| INFO:" not in l]
        if lines:
            print(f"--- {k}\n" + "\n".join(lines))
if r.get("status") != "ok":
    print("ERROR:", r.get("message"))
    sys.exit(1)
res = r.get("result")
print(json.dumps(res, indent=1, default=str) if not isinstance(res, str) else res)
