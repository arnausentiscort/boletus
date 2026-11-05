"""Preu dels bolets a Mercabarna (mercat majorista de Barcelona), a data/mercat.json.

Mercabarna publica cada dia el preu dominant, el màxim i el mínim (€/kg) de cada producte. Aquí es guarden
les files de bolets (rovellons, bolets sense determinar, gírgoles...) i els darrers 90 dies, per veure com van.
S'executa cada matí amb GitHub Actions."""
import json, re, subprocess, html, datetime as dt

URL = 'https://www.mercabarna.es/serveis/estadistiques-diaries/'
r = subprocess.run(['curl', '-sfL', '--max-time', '60', '-A', 'Mozilla/5.0 (boletus)', '-X', 'POST', URL,
                    '--data', 'familia=0&exportField=&sector=3&generar=Generar'], capture_output=True)
if r.returncode:
    raise SystemExit('Mercabarna no respon')
s = r.stdout.decode('latin-1')
try:
    s = r.stdout.decode('utf-8')
except UnicodeDecodeError:
    pass
t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '|', s))
m = re.search(r'preus del dia (\d{2})-(\d{2})-(\d{4})', t)
if not m:
    raise SystemExit('No trobo la data a la pàgina de Mercabarna')
dia = f'{m.group(3)}-{m.group(2)}-{m.group(1)}'
num = lambda x: float(x.replace('.', '').replace(',', '.'))
rows = {}
for nm, a, b, c in re.findall(r'\|(BOLETS[^|]*?) ?\|[ |]*([\d.,]+)[ |]*([\d.,]+)[ |]*([\d.,]+)', t):
    rows[html.unescape(nm).strip().capitalize()] = [num(a), num(b), num(c)]  # dominant, màxim, mínim

p = 'data/mercat.json'
try:
    d = json.load(open(p, encoding='utf-8'))
except (OSError, ValueError):
    d = {'font': 'Mercabarna', 'dies': {}}
d['dies'][dia] = rows
keep = sorted(d['dies'])[-90:]
d['dies'] = {k: d['dies'][k] for k in keep}
d['fet'] = dt.date.today().isoformat()
json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print(dia, rows)
