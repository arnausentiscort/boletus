"""Pluja i temperatura dels últims 45 dies en una quadrícula de tota Catalunya (data/grid_wx.json).

Cada casella fa 0,1° (uns 11 × 8 km) i només n'hi ha on hi ha boscos per a alguna espècie (data/region*.json).
El punt de cada casella és el centre dels seus boscos, no el centre del quadre (així no cau al mar ni en un pla).
L'app hi passa la mateixa regla que als vostres llocs i pinta el mapa segons on hi ha bolets ara.
S'executa cada matí amb GitHub Actions. Unitats: décimes (mm×10, °C×10). L'últim número de cada casella és l'altura mitjana dels boscos (m)."""
import json, subprocess, time, datetime as dt

C = 0.1
cells = {}
for f, k in [('data/region.json', 'ceps'), ('data/region_rov.json', 'pin')]:
    for z in json.load(open(f, encoding='utf-8'))['zones']:
        if z['ha'] < 15: continue
        key = (int(z['lat'] // C), int(z['lng'] // C))
        c = cells.setdefault(key, {'w': 0, 'la': 0, 'lo': 0, 'ob': 0, 'alt': 0, 'sp': set()})
        c['w'] += z['ha']; c['la'] += z['lat'] * z['ha']; c['lo'] += z['lng'] * z['ha']; c['ob'] += z['ob'] * z['ha']; c['alt'] += z['alt'] * z['ha']; c['sp'].add(k)
keys = sorted(cells)
pts = [(round(cells[k]['la'] / cells[k]['w'], 4), round(cells[k]['lo'] / cells[k]['w'], 4)) for k in keys]
print('caselles:', len(keys))

def get(url):
    for i in range(6):
        r = subprocess.run(['curl', '-sfL', '--max-time', '180', '-A', 'boletus/1.0', url], capture_output=True)
        if not r.returncode:
            try:
                return json.loads(r.stdout)
            except ValueError:
                pass
        time.sleep(10 * (i + 1))
    raise SystemExit('Open-Meteo no respon')

out = []
for a in range(0, len(pts), 80):
    ch = pts[a:a + 80]
    u = ('https://api.open-meteo.com/v1/forecast?latitude=' + ','.join(str(p[0]) for p in ch) + '&longitude=' + ','.join(str(p[1]) for p in ch) +
         '&daily=precipitation_sum,temperature_2m_mean,temperature_2m_min&past_days=45&forecast_days=1&timezone=Europe%2FMadrid')
    d = get(u); out += d if isinstance(d, list) else [d]
    time.sleep(2)

tenth = lambda v: None if v is None else round(v * 10)
res = {'start': out[0]['daily']['time'][0], 'made': dt.date.today().isoformat(), 'cell': C, 'c': []}
for k, p, d in zip(keys, pts, out):
    D = d['daily']
    res['c'].append([p[0], p[1], round(cells[k]['ob'] / cells[k]['w'], 2), ''.join(sorted(cells[k]['sp'])),
                     [tenth(v) for v in D['precipitation_sum']], [tenth(v) for v in D['temperature_2m_mean']], [tenth(v) for v in D['temperature_2m_min']], round(cells[k]['alt'] / cells[k]['w'])])
json.dump(res, open('data/grid_wx.json', 'w', encoding='utf-8'), separators=(',', ':'))
print('fet:', len(res['c']), 'caselles des del', res['start'])
