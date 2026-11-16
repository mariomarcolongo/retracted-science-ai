"""Shared offline scoring I/O and identity checks (paper sections 3.5–3.6).

Usage: imported by scoring scripts; no model calls or credentials are read.
The judge schemas are loaded from selected syntax-tree definitions, without running
judge.py. Output helpers reject repository data/ and paper/ destinations.
"""
import ast
import csv
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261115


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def answer_id(r):
    value = json.dumps([r["manifest_sha256"], r["model_id"], r["provider_requested"], r["pair_id"],
                        r["test"], r["side"], r["attempt"], r["tools_offered"], r["system"], r["user"], r["answer"]])
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def read_jsonl(path):
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def safe_path(path):
    path = Path(path).resolve()
    for protected in (ROOT / "data", ROOT / "paper"):
        if path == protected or protected in path.parents:
            raise ValueError("outputs must be outside data/ and paper/")
    if path in [ROOT / n for n in ("README.md", "DECISIONS.md", "CHANGELOG.md")]:
        raise ValueError("protected output path")
    return path


def safe_outdir(path):
    path = safe_path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _atomic(path, fill, newline=None):
    """Write to a temporary file next to PATH, flush it to disk, then swap it in: a crash leaves either the old
    file or the complete new one, never a shortened file that a later step could read without noticing (D65)."""
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline=newline) as f:
        fill(f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def write_jsonl(path, rows):
    path = safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    def fill(f):
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    _atomic(path, fill)


def write_csv(path, rows, fields=None):
    rows = list(rows)
    fields = fields or sorted({key for r in rows for key in r})
    path = safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    def fill(f):
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: canonical(v) if isinstance(v, (dict, list, tuple)) else v for k, v in row.items()})
    _atomic(path, fill, newline="")


def definitions():
    """Evaluate only the fixed schema builders and literal instructions, never CLI code."""
    tree = ast.parse((ROOT / "code/judge.py").read_text())
    names = {"S", "B", "COMMON", "FORM_TEST", "FORM_SQ", "GUIDE_TEST", "GUIDE_SQ"}
    nodes = [n for n in tree.body if
             isinstance(n, ast.FunctionDef) and n.name in {"enum", "obj"} or
             isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets)]
    scope = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "fixed_forms", "exec"), scope)
    return scope


def schemas():
    d = definitions()
    return d["FORM_TEST"], d["FORM_SQ"]


def valid(value, schema):
    kind = schema["type"]
    if kind == "object":
        return isinstance(value, dict) and set(value) == set(schema["properties"]) and all(
            valid(value[k], s) for k, s in schema["properties"].items())
    if kind == "array":
        return isinstance(value, list) and all(valid(v, schema["items"]) for v in value)
    if kind == "boolean":
        return isinstance(value, bool)
    return isinstance(value, str) and ("enum" not in schema or value in schema["enum"])


def terminal_runs(rundir, allow_incomplete=False):
    directory = Path(rundir)
    manifest = json.loads((directory / "manifest.json").read_text())
    mh = hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    plan = [tuple(x) for x in json.loads((directory / "plan.json").read_text())]
    if not plan or len(plan) != len(set(plan)):
        raise ValueError("empty or duplicate run plan")
    models = {m["name"]: m for m in manifest["models"]}
    final = {}
    for r in read_jsonl(directory / "runs.jsonl"):
        key = (r["model_name"], r["pair_id"], r["test"], r["side"])
        if key not in plan or r["manifest_sha256"] != mh:
            raise ValueError("run record does not match manifest/plan")
        m = models[r["model_name"]]
        if (r["model_id"], r["provider_requested"]) != (m["id"], m["provider"]):
            raise ValueError("run model/provider mismatch")
        if r["terminal"]:
            if key in final:
                raise ValueError("duplicate terminal answer")
            final[key] = r
    missing = set(plan) - set(final)
    if missing and not allow_incomplete:
        raise ValueError(f"incomplete run: {len(missing)} planned answers not terminal")
    return [final[k] for k in sorted(final)]


def checked_items(path, rundir):
    manifest = json.loads((Path(rundir) / "manifest.json").read_text())
    if sha_file(path) != manifest["items_sha256"]:
        raise ValueError("items hash does not match run")
    values = json.loads(Path(path).read_text())
    result = {v["pair_id"]: v for v in values}
    if len(result) != len(values):
        raise ValueError("duplicate pair IDs")
    return result, manifest
