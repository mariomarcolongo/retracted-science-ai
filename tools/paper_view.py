"""Render paper/paper-draft.md as a paper-style HTML page with review marks.

Usage: python3 -I tools/paper_view.py paper/paper-draft.md paper/paper-view.html
Review marks (open items) are defined in MARKS below: (line anchor, exact substring, note).
"""
import sys, re, html

src, dst = sys.argv[1], sys.argv[2]
lines = open(src, encoding="utf-8").read().split("\n")

# (text that identifies the line, substring on that line, note). Notes describe open items only.
MARKS = [
]

notes = []
for anchor, sub, note in MARKS:
    hit = [j for j, l in enumerate(lines) if anchor in l and sub in l]
    if not hit:
        sys.exit(f"mark not found: {anchor!r} / {sub!r}")
    j = hit[0]
    notes.append(note)
    k = len(notes)
    lines[j] = lines[j].replace(sub, f"\x01{k}\x02{sub}\x03", 1)

# Citation links: each in-text citation links to its source (DOI or URL from the reference list).
i_refs = lines.index("## References")
REFS, k = [], i_refs + 1
while k < len(lines) and (lines[k].startswith("- ") or not lines[k].strip()):
    if lines[k].startswith("- "):
        REFS.append(lines[k][2:])
    k += 1
REF_TEXT = set(REFS)
BY_YEAR, BY_NAME = {}, {}
for r in REFS:
    name = re.match(r"(.+?)(?:,| \()", r).group(1)
    year = re.search(r"\((\d{4}[a-z]?)", r).group(1)
    url = re.search(r"https?://\S+?(?=[.,;]?(?:\s|$))", r).group(0)
    BY_YEAR[(name, year)] = (url, r)
    BY_NAME.setdefault(name, []).append((url, r))
NAMES = "|".join(sorted((re.escape(n) for n in BY_NAME), key=len, reverse=True))
CITE = re.compile(rf"\b({NAMES})((?: et al\.?| &amp; [A-Z][\w\-]+)?)(?:(,? \(?)(\d{{4}}[a-z]?)(?!\d)|(?<=et al\.)|(?=(:)))")
unresolved = []

def cite_link(m):
    name, mid, sep, year = m.group(1), m.group(2) or "", m.group(3) or "", m.group(4)
    if year:
        hit = BY_YEAR.get((name, year))
    else:
        hit = BY_NAME[name][0] if len(BY_NAME[name]) == 1 and (mid.strip().startswith("et al") or m.group(5) == ":") else None
    if not hit:
        unresolved.append(m.group(0)); return m.group(0)
    url, ref = hit
    return f"<a class='cite' href='{html.escape(url, quote=True)}' target='_blank' rel='noopener' title='{html.escape(ref, quote=True)}'>{m.group(0)}</a>"

def link_cites(s):
    for rx, fn in ((CITE, cite_link),):
        parts = re.split(r"(<a\b.*?</a>|<[^>]+>)", s)
        s = "".join(p if p.startswith("<") else rx.sub(fn, p) for p in parts)
    return s

def inline(s, cite=True):
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", s)
    s = re.sub(r"(https?://[^\s<|)\]]+?)([.,;]?)(?=\s|$|<|\||\))", r"<a href='\1' target='_blank' rel='noopener'>\1</a>\2", s)
    s = re.sub(r"\[([^\]\x01-\x03]{1,80})\]", r"<span class='ph'>\1</span>", s)
    s = re.sub(r"\x01(\d+)\x02(.*?)\x03",
               lambda m: f"<mark id='m{m.group(1)}' data-n='{m.group(1)}' tabindex='0'>{m.group(2)}<sup>{m.group(1)}</sup><span class='pop'>{html.escape(notes[int(m.group(1))-1])}</span></mark>", s)
    return link_cites(s) if cite else s

def table(rows, cls=""):
    head, body = rows[0], [r for r in rows[1:] if not all(re.fullmatch(r":?-+:?", c) for c in r)]
    t = [f"<div class='tw'><table class='{cls}'><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"]
    for r in body:
        t.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
    return "".join(t) + "</tbody></table></div>"

def render(block):
    out, i = [], 0
    while i < len(block):
        l = block[i]
        if not l.strip() or l.strip() == "---":
            i += 1; continue
        m = re.match(r"(#{2,4}) (.*)", l)
        if m:
            n, txt = len(m.group(1)), m.group(2)
            sid = re.sub(r"[^a-z0-9]+", "-", re.sub(r"\x01\d+\x02|\x03", "", txt).lower()).strip("-")
            out.append(f"<h{n} id='{sid}'>{inline(txt)}</h{n}>"); i += 1; continue
        if l.startswith("|"):
            rows = []
            while i < len(block) and block[i].startswith("|"):
                rows.append([c.strip() for c in block[i].strip().strip("|").split("|")]); i += 1
            out.append(table(rows)); continue
        if l.startswith("- "):
            buf = []
            while i < len(block) and block[i].startswith("- "):
                buf.append(f"<li>{inline(block[i][2:], block[i][2:] not in REF_TEXT)}</li>"); i += 1
            out.append("<ul>" + "".join(buf) + "</ul>"); continue
        if re.match(r"\d+\. ", l):
            buf = []
            while i < len(block) and re.match(r"\d+\. ", block[i]):
                buf.append(f"<li>{inline(re.sub(r'^\d+\. ', '', block[i]))}</li>"); i += 1
            out.append("<ol>" + "".join(buf) + "</ol>"); continue
        m = re.fullmatch(r"!\[([^\]]*)\]\(([^)\s]+)\)", l.strip())
        if m:
            out.append(f"<figure><img src='{html.escape(m.group(2), quote=True)}' alt='{html.escape(m.group(1), quote=True)}'></figure>"); i += 1; continue
        buf = []
        while i < len(block) and block[i].strip() and not re.match(r"(#|\||- |\d+\. |---|!\[)", block[i]):
            buf.append(block[i]); i += 1
        p = " ".join(buf)
        if re.match(r"\*\*(\x01\d+\x02)?(Table|Figure|D-\d)", p):
            out.append(f"<p class='cap'>{inline(p)}</p>")
        elif p.startswith(("Sources:", "Sources, sample", "Release dates", "**By country**", "**Paid access", "All figures come")):
            out.append(f"<p class='small'>{inline(p)}</p>")
        elif re.fullmatch(r"\[[^\]]+\]", p.strip()):
            out.append(f"<div class='todo'>{html.escape(p.strip()[1:-1])}</div>")
        else:
            out.append(f"<p>{inline(p)}</p>")
    return "".join(out)

def find(prefix):
    return next(k for k, l in enumerate(lines) if l.startswith(prefix))

i_intro, i_results, i_limits = find("## 1. Introduction"), find("## 4. Results"), find("## 5. Discussion")
i_dec = len(lines)

title_opts = [l[2:] for l in lines[find("## Title"):find("## Abstract")] if l.startswith("- ")]
author = inline(lines[find("Mario Marcolongo")])

R_TESTS = ["R1", "R2", "R3", "R4", "R5", "R6", "K3", "K4", "R4-I", "K4-I"]
ALL = ["Gemini 4 Hydrogen", "GPT-6 Luna", "Gemini 3.5 Flash-Lite", "GPT-6.1 Sol", "Claude Sonnet 5.5",
       "Seed 2.0 Lite", "Qwen3.8 Flash", "DeepSeek V4.1 Flash", "ERNIE 5.5 Flash"]

def grid(tests, models):
    h = "<div class='tw'><table class='grid'><thead><tr><th></th>" + "".join(f"<th class='rot'><span>{m}</span></th>" for m in models) + "</tr></thead><tbody>"
    for t in tests:
        h += f"<tr><th>{t}</th>" + "".join("<td><div class='sb'><i></i><i></i><i></i><i></i><i></i></div></td>" for _ in models) + "</tr>"
    return h + "</tbody></table></div>"

results = (
    "<h2 id='4-results'>4. Results</h2>"
    "<div class='todo'>Filled after the runs. Layout below shows where each result goes; no data yet.</div>"
    "<figure>" + grid(R_TESTS, ALL) + "<figcaption><b>Figure 2.</b> Outcomes by test × model. Each cell is a stacked bar: share of answers in each category of Table 3c, with the failure rate and its 95% interval marked.</figcaption></figure>"
    "<div class='todo'>Text: status-question test rates per model; target and evidence citation rates per test; judge–judge and judge–human agreement (Cohen's kappa per field).</div>"
)

body = render(lines[i_intro:i_results]) + results + render(lines[i_limits:i_dec])

toc = "".join(
    f"<a href='#{sid}' class='l{n}'>{re.sub('<[^>]+>', '', t)}</a>"
    for n, sid, t in re.findall(r"<h([23]) id='([^']+)'>(.*?)</h\1>", body)
)
open_list = "".join(f"<li><a href='#m{k}'>{html.escape(n)}</a></li>" for k, n in enumerate(notes, 1))

alt_titles = "".join(f"<li>{inline(t)}</li>" for t in title_opts[1:])

css = """
:root{--paper:#fffefb;--desk:#eceae4;--fg:#1f1f1f;--muted:#6a6862;--line:#d8d5cc;--rule:#1f1f1f;--accent:#7a2e1f;
--mark:#fbe8a6;--markline:#d9b23a;--ph:#ecebe6;--phfg:#57554f;--pop:#2a2925;--popfg:#f6f4ee;--cell:#f4f2ec}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--paper:#1e1d1b;--desk:#121211;--fg:#e9e6df;--muted:#a19d94;--line:#3a3833;--rule:#e9e6df;--accent:#e39a85;
--mark:#4a3f17;--markline:#a88a2a;--ph:#2e2c28;--phfg:#c3bfb5;--pop:#f1eee6;--popfg:#1e1d1b;--cell:#262522}}
:root[data-theme=dark]{--paper:#1e1d1b;--desk:#121211;--fg:#e9e6df;--muted:#a19d94;--line:#3a3833;--rule:#e9e6df;--accent:#e39a85;
--mark:#4a3f17;--markline:#a88a2a;--ph:#2e2c28;--phfg:#c3bfb5;--pop:#f1eee6;--popfg:#1e1d1b;--cell:#262522}
*{box-sizing:border-box}
body{margin:0;background:var(--desk);color:var(--fg);font:16px/1.6 Charter,"Iowan Old Style","Source Serif Pro",Georgia,serif}
.wrap{display:grid;grid-template-columns:250px minmax(0,820px);gap:28px;justify-content:center;padding:28px 16px 80px}
.wrap>*{min-width:0}
aside{position:sticky;top:20px;align-self:start;max-height:calc(100vh - 40px);overflow:auto;font:13px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
aside a{display:block;color:var(--muted);text-decoration:none;padding:3px 0}aside a:hover{color:var(--fg)}
aside a.l3{padding-left:12px;font-size:12px}
aside h4{margin:18px 0 6px;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
aside ol{padding-left:18px;margin:0}aside ol li{margin:4px 0;color:var(--muted);overflow-wrap:anywhere}aside ol a{display:inline;padding:0}
.ctl{display:flex;gap:6px;flex-wrap:wrap}
button{font:12px -apple-system,sans-serif;border:1px solid var(--line);background:var(--paper);color:var(--fg);border-radius:6px;padding:5px 9px;cursor:pointer}
button[aria-pressed=true]{background:var(--fg);color:var(--paper)}
.paper{background:var(--paper);padding:64px 72px 72px;box-shadow:0 1px 3px rgba(0,0,0,.08),0 8px 30px rgba(0,0,0,.06);border-radius:2px}
.kicker{font:600 11px -apple-system,sans-serif;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);text-align:center;margin:0 0 14px}
h1{font-size:30px;line-height:1.2;text-align:center;margin:0 0 14px;font-weight:600}
.author{text-align:center;color:var(--muted);margin:0 0 6px}
.alt{font:13px -apple-system,sans-serif;color:var(--muted);text-align:center;margin:0 0 28px}.alt ul{list-style:none;padding:0;margin:4px 0 0}
.abstract{border-top:1.5px solid var(--rule);border-bottom:1px solid var(--line);padding:16px 28px 18px;margin:0 0 30px}
.abstract b.h{display:block;text-align:center;font:600 12px -apple-system,sans-serif;letter-spacing:.1em;text-transform:uppercase;margin-bottom:8px}
h2{font-size:21px;margin:40px 0 10px;font-weight:600}
h3{font-size:17px;margin:26px 0 8px;font-weight:600;font-style:italic}
p{margin:0 0 12px;text-align:justify;hyphens:auto}
ul,ol{padding-left:24px;margin:0 0 14px}li{margin:4px 0}
.cap{font:13.5px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:22px 0 6px;text-align:left}
.small{font:12px/1.45 -apple-system,sans-serif;color:var(--muted);text-align:left}
.tw{overflow-x:auto;margin:0 0 18px}
table{border-collapse:collapse;width:100%;font:12.5px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;border-top:1.5px solid var(--rule);border-bottom:1.5px solid var(--rule)}
th{font-weight:600;text-align:left;border-bottom:1px solid var(--rule);padding:6px 8px;vertical-align:bottom}
td{padding:6px 8px;vertical-align:top;border-bottom:1px solid var(--line)}tr:last-child td{border-bottom:0}
td a{word-break:break-all}td a.cite{word-break:normal}a.cite{color:inherit;text-decoration:underline dotted;text-underline-offset:2px}a.cite:hover{color:var(--accent)}
table.empty td{height:26px}
figure{margin:22px 0}figure img{display:block;width:100%;height:auto;background:#fff;border-radius:4px}figcaption{font:13.5px/1.4 -apple-system,sans-serif;margin-top:6px}
table.grid{width:auto;margin:0 auto}table.grid td{width:58px;height:34px;background:var(--cell);border:2px solid var(--paper)}
table.grid tbody th{border:0;padding-right:10px}.sb{display:flex;flex-direction:column-reverse;height:100%;opacity:.35}.sb i{flex:1;background:var(--muted)}.sb i:nth-child(2n){opacity:.5}
th.rot{height:120px;vertical-align:bottom;padding:0 0 6px;border-bottom:0;width:58px}
th.rot span{display:inline-block;writing-mode:vertical-rl;transform:rotate(180deg);font-weight:500;color:var(--muted);white-space:nowrap}
.ph{background:var(--ph);color:var(--phfg);border-radius:4px;padding:0 5px;font:0.86em -apple-system,sans-serif;white-space:nowrap}
.todo{border:1.5px dashed var(--line);border-radius:6px;padding:12px 16px;color:var(--muted);font:14px -apple-system,sans-serif;margin:8px 0 18px}
mark{background:var(--mark);color:inherit;border-bottom:1.5px solid var(--markline);position:relative;cursor:help;padding:0 1px}
mark sup{font:600 9px -apple-system,sans-serif;margin-left:2px;color:var(--accent)}
mark .pop{display:none}
#tip{display:none;position:fixed;z-index:50;width:min(320px,80vw);background:var(--pop);color:var(--popfg);
font:12.5px/1.45 -apple-system,sans-serif;padding:9px 11px;border-radius:7px;box-shadow:0 6px 20px rgba(0,0,0,.25);text-align:left;white-space:normal}
#tip.on{display:block}
body.clean mark{background:none;border:0;cursor:auto}body.clean mark sup,body.clean mark .pop{display:none!important}
body.clean .ph,body.clean .todo{opacity:.55}
details.work{margin-top:48px;border-top:1px solid var(--line);padding-top:16px;font-family:-apple-system,sans-serif}
details.work summary{cursor:pointer;color:var(--muted);font-size:13px}
@media (max-width:960px){.wrap{grid-template-columns:1fr}aside{position:static;max-height:none}.paper{padding:32px 20px 40px}p{text-align:left}}
"""

js = """
const b=document.body,btn=document.getElementById('marks'),tip=document.getElementById('tip');
function show(m){if(b.classList.contains('clean'))return;tip.textContent=m.querySelector('.pop').textContent;const r=m.getBoundingClientRect();
tip.classList.add('on');const w=tip.offsetWidth,h=tip.offsetHeight;let x=Math.min(Math.max(8,r.left),innerWidth-w-8),y=r.bottom+6;if(y+h>innerHeight-8)y=r.top-h-6;tip.style.left=x+'px';tip.style.top=y+'px'}
document.querySelectorAll('mark').forEach(m=>{m.addEventListener('mouseenter',()=>show(m));m.addEventListener('focus',()=>show(m));m.addEventListener('mouseleave',()=>tip.classList.remove('on'));m.addEventListener('blur',()=>tip.classList.remove('on'))});
addEventListener('scroll',()=>tip.classList.remove('on'),true);
try{if(localStorage.getItem('clean')==='1'){b.classList.add('clean');btn.setAttribute('aria-pressed','false')}}catch(e){}
btn.onclick=()=>{const c=b.classList.toggle('clean');btn.setAttribute('aria-pressed',String(!c));try{localStorage.setItem('clean',c?'1':'0')}catch(e){}};
document.getElementById('theme').onclick=()=>{const r=document.documentElement,d=r.dataset.theme==='dark'||(!r.dataset.theme&&matchMedia('(prefers-color-scheme:dark)').matches);r.dataset.theme=d?'light':'dark'};
"""

doc = f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Retracted Science Paper</title><style>{css}</style></head><body>
<div class='wrap'><aside>
<div class='ctl'><button id='marks' aria-pressed='true'>Review marks</button><button id='theme'>Light / dark</button></div>
<h4>Contents</h4>{toc}
<h4>Open items ({len(notes)})</h4><ol>{open_list}</ol>
</aside>
<main class='paper'>
<p class='kicker'>AI x Epistemics Research Sprint · draft v0.2</p>
<h1>{inline(title_opts[0])}</h1>
<p class='author'>{author}</p>
<div class='alt'>Alternative title<ul>{alt_titles}</ul></div>
<div class='abstract'><b class='h'>Abstract</b><div class='todo' style='margin:0'>Written last (150–250 words): problem · gap · what we did · main numbers · what it means.</div></div>
{body}
</main></div><div id='tip' role='tooltip'></div><script>{js}</script></body></html>"""
open(dst, "w", encoding="utf-8").write(doc)
print("written", dst, "| marks:", len(notes), "| citation links:", len(re.findall(r"class=.cite.", doc)), "| unresolved:", sorted(set(unresolved)))
