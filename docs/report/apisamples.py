import json, urllib.request
B="http://127.0.0.1:8001/api/v1"
def call(m,p,body=None,tok=None,raw=False):
    req=urllib.request.Request(B+p,method=m,data=(json.dumps(body).encode() if body is not None else None))
    req.add_header("Content-Type","application/json")
    if tok: req.add_header("Authorization","Bearer "+tok)
    try:
        r=urllib.request.urlopen(req); t=r.read().decode(); return r.status,t
    except urllib.error.HTTPError as e:
        return e.code,e.read().decode()
out={}
s,t=call("POST","/auth/login",{"email":"rina.demo@example.com","password":"report-demo-pass-1"}); out["login"]=(s,json.loads(t))
tok=out["login"][1]["access_token"]
out["login"][1]["access_token"]="<token>"
for k,(m,p,b) in {"me":("GET","/auth/me",None),"plan":("GET","/shop/plan",None),"products":("GET","/products?page=1&page_size=2",None),
  "orders":("GET","/orders?status=confirmed&page=1&page_size=1",None),"report":("GET","/reports/summary",None),"chats":("GET","/chats?filter=flagged&page=1&page_size=1",None),
  "wrong":("POST","/auth/login",{"email":"rina.demo@example.com","password":"wrong-password"}),"notif":("GET","/notifications",None),
  "health":("GET","/health",None)}.items():
    s,t=call(m,p,b,tok if k not in("wrong","health") else None)
    out[k]=(s,json.loads(t))
s,t=call("GET","/orders/export",None,tok); out["export"]=(s,t[:600])
s,t=call("GET","/products/import/template",None,tok); out["template"]=(s,t[:600])
json.dump(out,open("data/api_samples.json","w",encoding="utf8"),indent=1,ensure_ascii=False)
for k,v in out.items(): print(k,v[0],json.dumps(v[1],ensure_ascii=False)[:420] if not isinstance(v[1],str) else v[1][:420]); print()
