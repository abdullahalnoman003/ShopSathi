"""Reads the real project and writes docs/report/data/inventory.json (tables, columns, endpoints, files, tests, migrations)."""
import json, re, sys, os, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")
import app.models  # noqa
from app.core.database import Base
from app.main import app

inv = {}
# ---- database
tables = {}
for t in Base.metadata.sorted_tables:
    cols = []
    for c in t.columns:
        fks = [f"{fk.column.table.name}.{fk.column.name} ({fk.ondelete or 'NO ACTION'})" for fk in c.foreign_keys]
        cols.append({"name": c.name, "type": str(c.type), "pk": c.primary_key, "nullable": c.nullable, "unique": bool(c.unique), "fk": fks,
                     "default": (str(c.server_default.arg) if c.server_default is not None and hasattr(c.server_default, "arg") else None)})
    cons = []
    for k in t.constraints:
        n = type(k).__name__
        if n == "CheckConstraint": cons.append(("CHECK", k.name, str(k.sqltext)))
        elif n == "UniqueConstraint": cons.append(("UNIQUE", k.name, ", ".join(c.name for c in k.columns)))
    idx = [(i.name, [str(c) if not hasattr(c, "name") else c.name for c in i.expressions], bool(i.unique)) for i in t.indexes]
    tables[t.name] = {"columns": cols, "constraints": cons, "indexes": idx, "doc": ""}
inv["tables"] = tables
# ---- endpoints from openapi
spec = app.openapi()
eps = []
for path, ops in spec["paths"].items():
    for m, op in ops.items():
        params = [f"{p['name']} ({p['in']})" for p in op.get("parameters", [])]
        body = None
        rb = op.get("requestBody", {}).get("content", {})
        for ct, v in rb.items():
            ref = v.get("schema", {}).get("$ref") or v.get("schema", {}).get("items", {}).get("$ref") or ""
            body = (ct, ref.split("/")[-1] if ref else v.get("schema", {}).get("type"))
        resp = {}
        for code, r in op["responses"].items():
            ref = r.get("content", {}).get("application/json", {}).get("schema", {}).get("$ref", "")
            resp[code] = ref.split("/")[-1] if ref else ""
        eps.append({"method": m.upper(), "path": path, "summary": op.get("summary", ""), "params": params, "body": body, "responses": resp, "tag": (op.get("tags") or [""])[0]})
inv["endpoints"] = eps
inv["schemas"] = {k: {"props": {pk: (pv.get("type") or pv.get("$ref", "").split("/")[-1] or "any") for pk, pv in v.get("properties", {}).items()}, "required": v.get("required", [])} for k, v in spec["components"]["schemas"].items()}
# ---- files
def ls(rel, pattern="*.py", skip=("__pycache__",)):
    return sorted(str(p.relative_to(ROOT)).replace("\\", "/") for p in (ROOT / rel).rglob(pattern) if not any(s in p.parts for s in skip))
inv["files"] = {
    "routes": ls("backend/app/api/v1/routes"), "services": ls("backend/app/services"), "models": ls("backend/app/models"), "schemas": ls("backend/app/schemas"),
    "core": ls("backend/app/core"), "integrations": ls("backend/app/integrations"), "workers": ls("backend/app/workers"), "adapters": ls("backend/app/ai_adapters"),
    "migrations": ls("backend/alembic/versions"), "scripts": ls("backend/scripts"), "ai_engine": ls("ai_engine/shopsathi_ai"), "prompts": ls("ai_engine/shopsathi_ai/prompts", "*"),
    "backend_tests": ls("backend/tests"), "ai_tests": ls("ai_engine/tests"), "eval": ls("evaluation", "*.py"),
    "frontend_pages": ls("frontend/src/app", "*.tsx", ("node_modules",)), "frontend_components": ls("frontend/src/components", "*.tsx"), "frontend_lib": ls("frontend/src/lib", "*.ts*"),
    "deploy": sorted(str(p.relative_to(ROOT)).replace("\\", "/") for p in (ROOT / "deploy").iterdir() if p.is_file() and not p.name.startswith(".env.prod") or p.name == ".env.prod.example"),
}
# ---- migrations docstrings
mig = []
for f in inv["files"]["migrations"]:
    txt = (ROOT / f).read_text(encoding="utf-8")
    first = txt.split('"""')[1].strip().splitlines()[0] if '"""' in txt else ""
    m1 = re.search(r"""^revision(?:: str)? = ["'](\w+)["']""", txt, re.M); m2 = re.search(r'^down_revision.*?= (.*)', txt, re.M)
    rev = m1.group(1) if m1 else "?"; down = m2.group(1).strip("'\" ") if m2 else "?"
    mig.append({"file": f.split("/")[-1], "rev": rev, "down": down, "title": first})
inv["migrations"] = mig
# ---- settings
from app.core.config import Settings
inv["settings"] = [{"name": n.upper(), "default": ("" if f.is_required() else str(f.default)[:60])} for n, f in Settings.model_fields.items()]
json.dump(inv, open(ROOT / "docs/report/data/inventory.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=str)
print({k: (len(v) if hasattr(v, "__len__") else v) for k, v in inv.items()})
