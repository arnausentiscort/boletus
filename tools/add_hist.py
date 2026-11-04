"""Afegeix a data/hist.json la pluja i la temperatura (mitjana i mínima) de cada lloc de data/llocs.json.

Els llocs que ja hi són conserven la pluja i la temperatura mitjana tal com estaven (perquè els ceps no canviïn)
i només hi guanyen la temperatura mínima (n). Els llocs nous ho reben tot: ERA5 fins al 2021 i els models
d'alta resolució d'Open-Meteo des del 2022, com els altres. Unitats: décimes (mm×10, °C×10)."""
import json, subprocess, time

HF = 'https://historical-forecast-api.open-meteo.com/v1/forecast'
AR = 'https://archive-api.open-meteo.com/v1/archive'
VARS = 'precipitation_sum,temperature_2m_mean,temperature_2m_min'

def get(url):
    for _ in range(6):
        r = subprocess.run(['curl', '-sfL', '--max-time', '180', '-A', 'boletus-setup/1.0', url], capture_output=True)
        if not r.returncode:
            try: return json.loads(r.stdout)
            except ValueError: pass  # Open-Meteo de vegades talla la resposta a mitges (timeoutReached)
        print('reintent', flush=True); time.sleep(20)
    raise SystemExit('ha fallat ' + url)

def fetch(points, base, start, end, model=''):
    out = []
    for k in range(0, len(points), 1):
        ch = points[k:k + 1]
        u = (f"{base}?latitude={','.join(str(p[0]) for p in ch)}&longitude={','.join(str(p[1]) for p in ch)}"
             f"&start_date={start}&end_date={end}&daily={VARS}&timezone=Europe%2FMadrid{model}")
        d = get(u); out += d if isinstance(d, list) else [d]
        print('ok', k, flush=True); time.sleep(10)
    return out

H = json.load(open('data/hist.json', encoding='utf-8'))
llocs = json.load(open('data/llocs.json', encoding='utf-8'))['sites']
pts = [(s['lat'], s['lng']) for s in llocs]
old = fetch(pts, AR, H['start'], '2021-12-31', '&models=era5_seamless')
new = fetch(pts, HF, '2022-01-01', H['end'])
ten = lambda v: None if v is None else int(round(v * 10))
for s, a, b in zip(llocs, old, new):
    r = [ten(v) for v in a['daily']['precipitation_sum'] + b['daily']['precipitation_sum']]
    t = [ten(v) for v in a['daily']['temperature_2m_mean'] + b['daily']['temperature_2m_mean']]
    n = [ten(v) for v in a['daily']['temperature_2m_min'] + b['daily']['temperature_2m_min']]
    h = next((x for x in H['sites'] if x['id'] == s['id']), None)
    if h is None: H['sites'].append(dict(id=s['id'], r=r, t=t, n=n)); print('nou', s['id'], len(r))
    else:
        assert len(n) == len(h['r']), (s['id'], len(n), len(h['r']))
        h['n'] = n; print('mínima afegida a', s['id'])
json.dump(H, open('data/hist.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
