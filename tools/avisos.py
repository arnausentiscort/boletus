"""Avisos al mòbil (ntfy). S'executa cada matí amb GitHub Actions.

- Avís de pluja: ahir es va passar el llindar de pluja i algun dels dies de pluja va fer més de 12 °C.
- Avís de bolets: demà és el millor dia, perquè fa 16 dies va ploure prou i des d'aleshores la temperatura
  mitjana ha passat de 12 °C. No importa la temperatura del dia de la pluja: el que compta és quan creixen.
Així, pluja amb calor i després fred dona només el primer avís, i pluja freda i després calor, només el segon.
La regla és la mateixa que la de l'app (index.html).

Cada espècie té la seva regla (la mateixa que a l'app). Els ceps no han canviat; les de pinar (rovellons i bolets d'hivern:
fredolic, llenega negra i camagroc) tenen temporada i s'aturen si fa massa calor. L'avís de pluja és un de sol per lloc, amb el
millor dia de cada espècie. L'avís del dia abans porta la força de la tanda (0-100), amb les nits de gelada."""
import json, math, os, re, sys, urllib.request, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from recomana import avalua_rov  # la nota diària dels rovellons és la mateixa que a l'app

TOPIC = os.environ.get('NTFY_TOPIC', 'boletus-ceps-x7q2')
APP = 'https://arnausentiscort.github.io/boletus/'
SPECIES = {
    'ceps': dict(nom='ceps', mm=17, span=2, minT=12, wait=16, before=2, after=2, gap=5,
                 forca=dict(mm=[10, 35], t=[12, 16, 22, 27], mes={5: .3, 6: .4, 7: .4, 8: .6, 9: 1, 10: 1, 11: .4, 12: .1}, gel=.2)),
    'rov': dict(nom='rovellons', mm=25, span=5, minT=10, maxT=20, wait=12, before=4, after=6, gap=5, months=[9, 10, 11, 12, 1],
                forca=dict(mm=[12, 45], t=[6, 10, 16, 20], mes={9: .7, 10: 1, 11: .95, 12: .5, 1: .2}, gel=.1)),
    # fredolic, llenega negra i camagroc, junts
    'hiv': dict(nom="bolets d'hivern", mm=22, span=4, minT=3, maxT=15, wait=16, before=5, after=8, gap=5, months=[10, 11, 12, 1, 2],
                forca=dict(mm=[10, 42], t=[-1, 3, 13, 17], mes={10: .5, 11: 1, 12: .9, 1: .5, 2: .2}, gel=.05)),
}
MINSHOW = 35  # nota mínima per avisar d'una tanda (com a l'app)
AVISA = {'ceps', 'rov'}  # els bolets d'hivern es calculen a l'app, però no avisen
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

def forca(R, mm, tg, peak, gelades=(0, 0)):
    """Força de la tanda (0-100), com a l'app: pluja de l'episodi x temperatura de creixement x mes x gelades."""
    F = R['forca']
    fp = min(1, max(0, (mm - F['mm'][0]) / (F['mm'][1] - F['mm'][0]))) ** .85
    nits, total = gelades  # nits de -2 °C o menys i dies amb temperatura mínima
    fg = 1 - min(.8, nits * F.get('gel', 0)) if total >= 3 else 1
    v = round(100 * fp * trap(tg, *F['t']) * F['mes'].get(peak.month, 0) * fg)
    return v, 'bona' if v >= 60 else 'normal' if v >= 35 else 'fluixa'

NL = chr(10)  # salt de línia dins dels missatges

def nom_curt(nom):
    return re.sub(r"^Pinar (de la |de l[’']|del |de |d[’'])", '', nom)

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
         '&daily=precipitation_sum,temperature_2m_mean,temperature_2m_min&past_days=30&forecast_days=2&timezone=Europe%2FMadrid')
    data = json.load(urllib.request.urlopen(u, timeout=60))
    data = data if isinstance(data, list) else [data]
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=1))).date() if 'TODAY' not in os.environ else dt.date.fromisoformat(os.environ['TODAY'])
    yesterday, tomorrow = today - dt.timedelta(1), today + dt.timedelta(1)
    sent = 0; rain = {}; demà = {}; ara = []
    for s, d in zip(llocs, data):
        days = [dt.date.fromisoformat(x) for x in d['daily']['time']]
        r = [v or 0 for v in d['daily']['precipitation_sum']]; t = d['daily']['temperature_2m_mean']; n = d['daily']['temperature_2m_min']
        for k, R in SPECIES.items():
            if k not in AVISA: continue  # la família només busca ceps i rovellons
            if k not in s.get('sp', ['ceps']): continue  # cada lloc només avisa de les seves espècies
            if k == 'rov':  # rovellons: nota diària (humitat de la terra), no tandes
                wins, sc = avalua_rov(R, days, r, t, n, today, today + dt.timedelta(14))
                get = lambda d: sc.get(d, (0,))[0]; nm = nom_curt(s['name'])
                if get(today) >= 60 and get(yesterday) < 60: ara.append((nm, get(today)))
                if get(tomorrow) >= 35 and get(tomorrow) > get(today) and get(tomorrow) >= get(tomorrow + dt.timedelta(1)):
                    v = get(tomorrow); demà.setdefault('rov', []).append((nm, v, 'bona' if v >= 60 else 'normal', sunrise(tomorrow, s['lat'], s['lng'])))
                if yesterday in days:
                    iy = days.index(yesterday)
                    if sum(r[iy - 1:iy + 1]) >= 15 and sum(r[iy - 2:iy]) < 15:  # ahir va ploure prou: avís de pluja
                        nx = next((w for w in wins if w['b'] >= tomorrow), None)
                        if nx: rain.setdefault(('rov', nx['peak'], nx['a'], nx['b']), []).append((nm, sum(r[iy - 1:iy + 1])))
                continue
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
                    # només s'avisa si la tanda pot arribar a la nota mínima (pluja de l'episodi x pes del mes): el novembre i el desembre, gairebé mai
                    F = R['forca']; fp = min(1, max(0, (sm - F['mm'][0]) / (F['mm'][1] - F['mm'][0]))) ** .85
                    # (el dia després de ploure encara no se sap la temperatura: per això es demana un marge ampli)
                    if k == 'ceps' and 100 * fp * F['mes'].get(peak.month, 0) < MINSHOW + 15: last = i; continue
                    if day == yesterday and warm_rain:
                        rain.setdefault((k, peak, a, b), []).append((nom_curt(s['name']), sm))
                    if peak == tomorrow and good_after:
                        ep = sum(r[max(0, i - R['span'] + 1):i + 4])
                        gn = [x for x in n[i + 1:i + R['wait'] - 1] if x is not None]
                        v, nom = forca(R, ep, sum(g) / len(g), peak, (sum(1 for x in gn if x <= -2), len(gn)))
                        if v >= MINSHOW: demà.setdefault(k, []).append((nom_curt(s['name']), v, nom, sunrise(tomorrow, s['lat'], s['lng'])))
                last = i
    # Un sol avís de pluja per dia i un sol avís de "demà" per espècie, perquè no n'arribin molts
    if rain:
        mms = [m for v in rain.values() for _, m in v]
        lines = []
        for (k, peak, a, b), llocs in sorted(rain.items(), key=lambda kv: kv[0][1]):
            ll = ', '.join(nm for nm, _ in llocs)
            lines.append(f"{SPECIES[k]['nom'].capitalize()}: millor dia {fmt(peak)} (del {a.day}{'' if a.month == b.month else ' ' + MESOS[a.month - 1]} al {b.day} {MESOS[b.month - 1]}) · {ll}")
        lit = f"{round(min(mms))}" if round(min(mms)) == round(max(mms)) else f"{round(min(mms))}-{round(max(mms))}"
        send('Ha plogut als vostres boscos', f"{lit} litres. Si després la temperatura acompanya:{NL}" + NL.join(lines), 'cloud_with_rain'); sent += 1
    if ara:
        send('Ara toca als vostres rovellons', NL.join(f"{nm} · nota {v}" for nm, v in sorted(ara, key=lambda x: -x[1])) + f"{NL}Com més d'hora, menys gent hi haurà passat.", 'mushroom'); sent += 1
    for k, llocs in demà.items():
        sol = min(x[3] for x in llocs)
        cos = NL.join(f"{nm} · tanda {nom} ({v}/100)" for nm, v, nom, _ in sorted(llocs, key=lambda x: -x[1]))
        send(f"Demà és el millor dia de {SPECIES[k]['nom']}", f"Surt el sol a les {sol}. Com més d'hora, millor.{NL}{cos}", 'mushroom'); sent += 1
    # Avís de temporada: un missatge els dies que canvia l'època (pesos del mes de la força de cada espècie)
    TEMP = {(9, 1): ('Comença la temporada', "Setembre: ceps i rovellons fins a novembre. Quan plogui prou als vostres llocs, us avisaré."),
            (10, 1): ('Octubre, el millor mes', "És el millor mes per als ceps i per als rovellons."),
            (11, 20): ('La temporada s\'acaba', "Amb el fred en sortiran pocs més. Si plou i no glaça, encara pot sortir alguna tanda.")}
    if (today.month, today.day) in TEMP:
        t, m = TEMP[(today.month, today.day)]; send(t, m, 'calendar'); sent += 1
    if '--prova' in sys.argv:
        send('Boletus funciona', "Els avisos estan activats. Rebràs un missatge quan plogui prou als vostres boscos.", 'white_check_mark')
    print('avisos enviats:', sent)

if __name__ == '__main__':
    main()
