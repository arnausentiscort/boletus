"""Avisos al mòbil (ntfy). S'executa cada matí amb GitHub Actions.

- Avís de pluja: ahir es va passar el llindar de pluja i algun dels dies de pluja va fer més de 12 °C.
- Avís de bolets: demà és el millor dia, perquè fa 16 dies va ploure prou i des d'aleshores la temperatura
  mitjana ha passat de 12 °C. No importa la temperatura del dia de la pluja: el que compta és quan creixen.
Així, pluja amb calor i després fred dona només el primer avís, i pluja freda i després calor, només el segon.
La regla és la mateixa que la de l'app (index.html).

Cada espècie té la seva regla. Els ceps no han canviat; els rovellons tenen temporada (de setembre a gener)
i també s'aturen si fa massa calor. L'avís de pluja és un de sol per lloc, amb el millor dia de cada espècie."""
import json, math, os, sys, urllib.request, datetime as dt

TOPIC = os.environ.get('NTFY_TOPIC', 'boletus-ceps-x7q2')
APP = 'https://arnausentiscort.github.io/boletus/'
SPECIES = {
    'ceps': dict(nom='ceps', mm=17, span=2, minT=12, wait=16, before=2, after=2, gap=5,
                 forca=dict(mm=[10, 35], t=[12, 16, 22, 27], mes={5: .3, 6: .4, 7: .4, 8: .6, 9: 1, 10: 1, 11: .4, 12: .1})),
    'rov': dict(nom='rovellons', mm=25, span=5, minT=10, maxT=20, wait=12, before=4, after=6, gap=5, months=[9, 10, 11, 12, 1],
                forca=dict(mm=[12, 45], t=[6, 10, 16, 20], mes={9: .7, 10: 1, 11: .95, 12: .5, 1: .2})),
}
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

def trap(x, a, b, c, d):
    return 0 if x <= a or x >= d else (x - a) / (b - a) if x < b else (d - x) / (d - c) if x > c else 1

def forca(R, mm, tg, peak):
    """Força de la tanda (0-100), com a l'app: pluja de l'episodi x temperatura de creixement x mes."""
    F = R['forca']
    fp = min(1, max(0, (mm - F['mm'][0]) / (F['mm'][1] - F['mm'][0]))) ** .85
    v = round(100 * fp * trap(tg, *F['t']) * F['mes'].get(peak.month, 0))
    return v, 'bona' if v >= 60 else 'normal' if v >= 35 else 'fluixa'

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
        rain_msgs = []  # un sol avís de pluja per lloc, amb totes les espècies
        for k, R in SPECIES.items():
            if k not in s.get('sp', ['ceps']): continue  # cada lloc només avisa de les seves espècies
            last = -99
            for i in range(R['span'] - 1, len(days)):
                if days[i] > yesterday: break  # només dies ja acabats
                sm = sum(r[i - R['span'] + 1:i + 1]); tt = [x for x in t[i - R['span'] + 1:i + 1] if x is not None]
                if sm < R['mm']: continue
                if i - last > R['gap']:
                    day = days[i]; peak = day + dt.timedelta(R['wait'])
                    if 'months' in R and peak.month not in R['months']: last = i; continue  # fora de temporada
                    a, b = peak - dt.timedelta(R['before']), peak + dt.timedelta(R['after'])
                    g = [x for x in t[i + 1:i + R['wait'] - 1] if x is not None]  # dies en què creixen
                    good_after = len(g) >= 3 and R['minT'] <= sum(g) / len(g) <= R.get('maxT', 99)
                    # avís de pluja dels ceps: algun dels dies de pluja ha de passar de 12 °C
                    warm_rain = k != 'ceps' or (bool(tt) and max(tt) >= R['minT'])
                    if day == yesterday and warm_rain:
                        rain_msgs.append((sm, f"{R['nom'].capitalize()}: millor dia {fmt(peak)} (del {a.day}{'' if a.month == b.month else ' ' + MESOS[a.month - 1]} al {b.day} {MESOS[b.month - 1]})"))
                    if peak == tomorrow and good_after:
                        ep = sum(r[max(0, i - R['span'] + 1):i + 4])
                        v, nom = forca(R, ep, sum(g) / len(g), peak)
                        send(f"Demà és el millor dia de {R['nom']} a {s['name']}", f"Tanda {nom} ({v}/100). Surt el sol a les {sunrise(tomorrow, s['lat'], s['lng'])}. Com més d'hora, millor.", 'mushroom'); sent += 1
                last = i
        if rain_msgs:
            send(f"Ha plogut a {s['name']}", f"{round(max(m for m, _ in rain_msgs))} litres. Si després la temperatura acompanya:\n" + '\n'.join(x for _, x in rain_msgs), 'cloud_with_rain'); sent += 1
    if '--prova' in sys.argv:
        send('Boletus funciona', "Els avisos estan activats. Rebràs un missatge quan plogui prou als vostres boscos.", 'white_check_mark')
    print('avisos enviats:', sent)

if __name__ == '__main__':
    main()
