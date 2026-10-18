"""Avisos al mòbil (ntfy). S'executa cada matí amb GitHub Actions.

- Quan ahir es va passar el llindar de pluja en un lloc: avisa del millor dia.
- Quan demà és el millor dia d'un lloc: ho recorda, amb l'hora en què surt el sol.
La regla és la mateixa que la de l'app (index.html)."""
import json, math, os, sys, urllib.request, datetime as dt

TOPIC = os.environ.get('NTFY_TOPIC', 'boletus-ceps-x7q2')
APP = 'https://arnausentiscort.github.io/boletus/'
RULE = dict(mm=17, span=2, minT=12, wait=16, before=2, after=2, gap=5)
DIES = ['dl', 'dt', 'dc', 'dj', 'dv', 'ds', 'dg']
MESOS = ['gen', 'febr', 'març', 'abr', 'maig', 'juny', 'jul', 'ag', 'set', 'oct', 'nov', 'des']
def fmt(d): return f"{DIES[d.weekday()]} {d.day} {MESOS[d.month - 1]}"

def sunrise(d, lat, lon):
    g = 2 * math.pi / 365 * (d.timetuple().tm_yday - 1)
    eq = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g) - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    de = 0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g)
    ha = math.degrees(math.acos(math.cos(math.radians(90.833)) / (math.cos(math.radians(lat)) * math.cos(de)) - math.tan(math.radians(lat)) * math.tan(de)))
    def last_sun(m): x = dt.date(d.year, m, 31); return x - dt.timedelta((x.weekday() + 1) % 7)
    off = 2 if last_sun(3) <= d < last_sun(10) else 1
    m = 720 - 4 * (lon + ha) - eq + off * 60
    return f"{int(m // 60)}:{int(m % 60):02d}"

def send(title, msg, tags):
    if os.environ.get('DRY'):
        print('[prova] ' + title + ' | ' + msg); return
    req = urllib.request.Request(f'https://ntfy.sh/{TOPIC}', data=msg.encode('utf-8'), method='POST',
                                 headers={'Title': title.encode('utf-8'), 'Tags': tags, 'Click': APP})
    urllib.request.urlopen(req, timeout=30).read()
    print('enviat:', title, '|', msg)

def main():
    llocs = json.load(open('data/llocs.json', encoding='utf-8'))['sites']
    lat = ','.join(f"{s['lat']:.4f}" for s in llocs); lon = ','.join(f"{s['lng']:.4f}" for s in llocs)
    u = (f'https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}'
         '&daily=precipitation_sum,temperature_2m_mean&past_days=30&forecast_days=2&timezone=Europe%2FMadrid')
    data = json.load(urllib.request.urlopen(u, timeout=60))
    data = data if isinstance(data, list) else [data]
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=1))).date() if 'TODAY' not in os.environ else dt.date.fromisoformat(os.environ['TODAY'])
    yesterday, tomorrow = today - dt.timedelta(1), today + dt.timedelta(1)
    sent = 0
    for s, d in zip(llocs, data):
        days = [dt.date.fromisoformat(x) for x in d['daily']['time']]
        r = [v or 0 for v in d['daily']['precipitation_sum']]; t = d['daily']['temperature_2m_mean']
        last, trig = -99, []
        for i in range(RULE['span'] - 1, len(days)):
            if days[i] > yesterday: break  # només dies ja acabats
            sm = sum(r[i - RULE['span'] + 1:i + 1]); tt = [x for x in t[i - RULE['span'] + 1:i + 1] if x is not None]
            if sm >= RULE['mm'] and tt and sum(tt) / len(tt) >= RULE['minT']:
                if i - last > RULE['gap']: trig.append((days[i], sm))
                last = i
        for day, mm in trig:
            peak = day + dt.timedelta(RULE['wait'])
            a, b = peak - dt.timedelta(RULE['before']), peak + dt.timedelta(RULE['after'])
            if day == yesterday:
                send(f"Ha plogut a {s['name']}", f"{round(mm)} litres. Millor dia per anar-hi: {fmt(peak)} (del {a.day} al {b.day} {MESOS[b.month - 1]}).", 'cloud_with_rain'); sent += 1
            if peak == tomorrow:
                send(f"Demà és el millor dia a {s['name']}", f"Surt el sol a les {sunrise(tomorrow, s['lat'], s['lng'])}. Com més d'hora, més ceps.", 'mushroom'); sent += 1
    if '--prova' in sys.argv:
        send('Boletus funciona', "Els avisos estan activats. Rebràs un missatge quan plogui prou als vostres boscos.", 'white_check_mark')
    print('avisos enviats:', sent)

if __name__ == '__main__':
    main()
