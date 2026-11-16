import sys, re, html

src, dst = sys.argv[1], sys.argv[2]
lines = open(src, encoding="utf-8").read().split("\n")

def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", s)
    s = re.sub(r"(https?://[^\s<|)\]]+?)([.,;]?)(?=\s|$|<|\||\))", r"<a href='\1' target='_blank' rel='noopener'>\1</a>\2", s)
    return s

out, i, title = [], 0, "Paper draft"
while i < len(lines):
    l = lines[i]
    if not l.strip():
        i += 1; continue
    if l.strip() == "---":
        out.append("<hr>"); i += 1; continue
    m = re.match(r"(#{1,4}) (.*)", l)
    if m:
        n = len(m.group(1))
        if n == 1: title = m.group(2)
        out.append(f"<h{n}>{inline(m.group(2))}</h{n}>"); i += 1; continue
    if l.startswith(">"):
        buf = []
        while i < len(lines) and lines[i].startswith(">"):
            buf.append(lines[i].lstrip("> ").strip()); i += 1
        out.append(f"<div class='note'>{inline(' '.join(buf))}</div>"); continue
    if l.startswith("|"):
        rows = []
        while i < len(lines) and lines[i].startswith("|"):
            rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")]); i += 1
        head, body = rows[0], [r for r in rows[1:] if not all(re.fullmatch(r":?-+:?", c) for c in r)]
        t = ["<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"]
        for r in body:
            t.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
        out.append("".join(t) + "</tbody></table>"); continue
    if re.match(r"- ", l):
        buf = []
        while i < len(lines) and lines[i].startswith("- "):
            buf.append(f"<li>{inline(lines[i][2:])}</li>"); i += 1
        out.append("<ul>" + "".join(buf) + "</ul>"); continue
    if re.match(r"\d+\. ", l):
        buf = []
        while i < len(lines) and re.match(r"\d+\. ", lines[i]):
            buf.append(f"<li>{inline(re.sub(r'^\d+\. ', '', lines[i]))}</li>"); i += 1
        out.append("<ol>" + "".join(buf) + "</ol>"); continue
    buf = []
    while i < len(lines) and lines[i].strip() and not re.match(r"(#|>|\||- |\d+\. |---)", lines[i]):
        buf.append(lines[i]); i += 1
    out.append(f"<p>{inline(' '.join(buf))}</p>")

css = """
:root{--bg:#fff;--fg:#1d1d1f;--muted:#6b6b70;--line:#d9d9de;--head:#f3f3f6;--note:#fff8e1;--noteb:#e8c766}
@media (prefers-color-scheme:dark){:root{--bg:#1b1b1d;--fg:#ececf0;--muted:#a0a0a8;--line:#3a3a40;--head:#26262a;--note:#2e2a1c;--noteb:#8a7428}}
body{background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;max-width:980px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:26px;margin:8px 0 12px}h2{font-size:20px;margin:32px 0 8px;padding-top:8px;border-top:1px solid var(--line)}
h3{font-size:16px;margin:22px 0 6px}hr{border:0;margin:8px 0}
table{border-collapse:collapse;width:100%;margin:10px 0 18px;font-size:13.5px;display:block;overflow-x:auto}
th,td{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
th{background:var(--head);font-weight:600}
.note{background:var(--note);border-left:4px solid var(--noteb);padding:8px 12px;margin:8px 0 16px;font-size:14px}
ul,ol{padding-left:22px}li{margin:3px 0}
"""
doc = f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{css}</style></head><body>{''.join(out)}</body></html>"
open(dst, "w", encoding="utf-8").write(doc)
print("written", dst)
