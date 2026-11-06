"""Recomana'm un bosc: els millors boscos per anar-hi un cap de setmana (o uns dies) a prop d'un lloc.

  python tools/recomana.py Reus                    # rovellons, aquest cap de setmana, a 40 km
  python tools/recomana.py "Santa Bàrbara" --sp ceps --km 30
  python tools/recomana.py Bossòst --dies 2026-11-07,2026-11-08 --n 5

Com ho fa:
  1. Busca el lloc (Open-Meteo) i agafa les zones de bosc de l'espècie (data/region_rov.json o data/region.json).
  2. Es queda les millors de terreny en el radi (mida, altura, obaga, pendent) i en baixa la pluja i la temperatura.
  3. Hi passa la mateixa regla que l'app (amb el retard de muntanya dels rovellons) i mira si els dies triats cauen dins d'una tanda.
  4. Per a les millors, busca a OpenStreetMap on aparcar: un aparcament o una pista a prop, que no sigui privada.
Treu el resultat en text (per al xat) i en JSON (--json)."""
import argparse, json, math, subprocess, sys, time, urllib.parse, datetime as dt

SP = {
    'rov': dict(nom='rovellons', region='data/region_rov.json', mm=25, span=5, minT=10, maxT=20, wait=12, before=4, after=6, ob_bonus=2,
                months=[9, 10, 11, 12, 1], forca=dict(mm=[12, 45], t=[6, 10, 16, 20], mes={9: .7, 10: 1, 11: .95, 12: .5, 1: .2}, gel=.1),
                spot=dict(alt=[80, 300, 1300, 1750], ob=.8)),
    'ceps': dict(nom='ceps', region='data/region.json', mm=17, span=2, minT=12, maxT=None, wait=16, before=2, after=2, ob_bonus=1,
                 months=None, forca=dict(mm=[10, 35], t=[12, 16, 22, 27], mes={5: .3, 6: .4, 7: .4, 8: .6, 9: 1, 10: 1, 11: .4, 12: .1}, gel=.2)),
}
DIES = ['dilluns', 'dimarts', 'dimecres', 'dijous', 'divendres', 'dissabte', 'diumenge']
MESOS = ['gen', 'febr', 'març', 'abr', 'maig', 'juny', 'jul', 'ag', 'set', 'oct', 'nov', 'des']
# Zones on la recol·lecció té normes pròpies (caixa aproximada): s'avisa perquè ho miris abans d'anar-hi
REGULADES = [((41.85, 42.22, 1.20, 1.80), 'Solsonès: cal el permís de recol·lecció de bolets.'),
             ((41.33, 41.40, 0.99, 1.10), "Bosc de Poblet (paratge natural): mira'n les normes abans de collir.")]

def get(url, data=None, tries=5):
    for i in range(tries):
        cmd = ['curl', '-sfL', '--max-time', '120', '-A', 'boletus/1.0', url] + (['--data-urlencode', 'data=' + data] if data else [])
        r = subprocess.run(cmd, capture_output=True)
        if not r.returncode:
            try: return json.loads(r.stdout)
            except ValueError: pass
        time.sleep(5 * (i + 1))
    raise SystemExit('no respon: ' + url[:80])

def km(a, b, c, d):
    t = math.radians; h = math.sin(t(c - a) / 2) ** 2 + math.cos(t(a)) * math.cos(t(c)) * math.sin(t(d - b) / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))
def rumb(a, b, c, d):
    t = math.radians; y = math.sin(t(d - b)) * math.cos(t(c)); x = math.cos(t(a)) * math.sin(t(c)) - math.sin(t(a)) * math.cos(t(c)) * math.cos(t(d - b))
    return ['nord', 'nord-est', 'est', 'sud-est', 'sud', 'sud-oest', 'oest', 'nord-oest'][round((math.degrees(math.atan2(y, x)) + 360) % 360 / 45) % 8]
def trap(x, a, b, c, d): return 0 if x <= a or x >= d else (x - a) / (b - a) if x < b else (d - x) / (d - c) if x > c else 1
def fdia(d): return f"{DIES[d.weekday()]} {d.day} {MESOS[d.month - 1]}"
def gm(la, lo): return f"https://www.google.com/maps/search/?api=1&query={la:.6f},{lo:.6f}"
def gmdir(la, lo): return f"https://www.google.com/maps/dir/?api=1&destination={la:.6f},{lo:.6f}"

def terreny(z, k):
    """Puntuació del terreny, com els spots del mapa de l'app."""
    if k == 'ceps':
        return 3 * z['bo'] + z['acida'] + min(z['ha'], 150) / 150 + max(0, 1 - abs(z['alt'] - 450) / 350) + (.8 if z['ob'] >= .3 else 0) - (1 if z['arbre'] == 'avellaners' else 0) - 2 * (z.get('emp') or 0) - max(0, (z.get('pend') or 0) - 18) / 7
    S = SP[k]['spot']
    return min(z['ha'], 150) / 150 + 1.2 * trap(z['alt'], *S['alt']) + (S['ob'] if z['ob'] >= .3 else 0) - 2 * (z.get('emp') or 0) - max(0, (z.get('pend') or 0) - 18) / 7

def avalua(R, k, days, r, t, n, alt, obaga, today):
    """La regla de l'app (evalSite + forca), amb el retard de muntanya dels rovellons."""
    dl = min(10, max(0, round((alt - 700) / 80))) if k == 'rov' else 0
    wait, after = R['wait'] + dl, R['after'] + math.ceil(dl / 2)
    bonus = R['ob_bonus'] if obaga >= .5 else 0
    i0 = days.index(today) if today in days else len(days) - 1
    out, last = [], -99
    for i in range(R['span'] - 1, i0 + 1):
        sm = sum(x or 0 for x in r[i - R['span'] + 1:i + 1])
        if sm < R['mm']: continue
        peak = days[i] + dt.timedelta(wait)
        if i - last > 5 and not (R['months'] and peak.month not in R['months']):
            g = [x for x in t[i + 1:i + wait - 1] if x is not None]
            tg = sum(g) / len(g) if g else None
            w = dict(t1=days[i], peak=peak, a=peak - dt.timedelta(R['before']), b=peak + dt.timedelta(after + bonus), tg=tg, prov=len(g) < wait - 2)
            hot = R['maxT'] is not None and len(g) >= 3 and tg > R['maxT']
            if not (len(g) >= 3 and (tg < R['minT'] or hot)):
                F = R['forca']; t0 = i - R['span'] + 1
                mm = sum(x or 0 for x in r[t0:min(i + 3, i0) + 1])
                fp = min(1, max(0, (mm - F['mm'][0]) / (F['mm'][1] - F['mm'][0]))) ** .85
                ft = .5 if tg is None else trap(tg, *F['t']); fm = F['mes'].get(peak.month, 0)
                gn = [x for x in n[i + 1:min(i + wait - 2, i0) + 1] if x is not None]
                fg = 1 - min(.8, sum(1 for x in gn if x <= -2) * F['gel']) if len(gn) >= 3 else 1
                w['v'] = round(100 * fp * ft * fm * fg); w['mm'] = mm; out.append(w)
        last = i
    return out, dl

def bosc_real(la, lo, sp):
    """El centre d'una taca de bosc pot caure en un poble: es porta al punt de bosc (no de vora) més proper, amb la màscara de l'app."""
    from PIL import Image
    n = 4096; fx = (lo + 180) / 360 * n; fy = (1 - math.asinh(math.tan(math.radians(la))) / math.pi) / 2 * n; x, y = int(fx), int(fy)
    try: A = Image.open(f"tiles/mask_{'ceps' if sp == 'ceps' else 'rov'}/12/{x}/{y}.png").convert('LA').split()[1].load()
    except OSError: return None
    px, py = (fx - x) * 256, (fy - y) * 256; best = None
    ok = lambda i, j: 0 <= i < 256 and 0 <= j < 256 and A[i, j] >= 200
    for j in range(256):
        for i in range(256):
            if not ok(i, j): continue
            dd = (i + .5 - px) ** 2 + (j + .5 - py) ** 2
            if best and dd >= best[0]: continue
            if sum(ok(i + a, j + b) for a in range(-2, 3) for b in range(-2, 3)) >= 22: best = (dd, i, j)
    if not best or best[0] > 1600: return None
    return (math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + (best[2] + .5) / 256) / n)))), (x + (best[1] + .5) / 256) / n * 360 - 180)

def lloc_nom(la, lo):
    """Nom del lloc (poble o paratge) amb el cercador d'OpenStreetMap."""
    r = subprocess.run(['curl', '-sfL', '--max-time', '30', '-A', 'boletus/1.0 (github.com/arnausentiscort/boletus)',
                        f'https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={la}&lon={lo}&zoom=14&accept-language=ca'], capture_output=True)
    time.sleep(1.1)  # norma de Nominatim: com a molt una consulta per segon
    try: A = json.loads(r.stdout).get('address', {})
    except ValueError: return ''
    return A.get('village') or A.get('town') or A.get('hamlet') or A.get('municipality') or A.get('city') or ''

def aparcar(la, lo):
    """On deixar el cotxe: un aparcament a menys de 2 km, o el punt de carretera o pista bona més a prop del bosc."""
    q = f"""[out:json][timeout:60];
(nwr["amenity"="parking"](around:2000,{la},{lo});
 way["highway"~"^(tertiary|unclassified|residential|service|track)$"]["access"!~"^(private|no)$"]["motor_vehicle"!~"^(private|no)$"](around:1500,{la},{lo}););
out center tags geom;"""
    try: d = get('https://overpass-api.de/api/interpreter', q)
    except SystemExit: return None
    best = None
    for e in d.get('elements', []):
        tg = e.get('tags', {})
        if tg.get('amenity') == 'parking':
            if tg.get('access') in ('private', 'no', 'customers'): continue
            c = e.get('center') or {'lat': e.get('lat'), 'lon': e.get('lon')}
            if c['lat'] is None: continue
            dkm = km(la, lo, c['lat'], c['lon']); s = dkm - .6  # un aparcament de veritat val més
            cand = (s, c['lat'], c['lon'], 'aparcament' + (f" «{tg['name']}»" if tg.get('name') else ''), dkm)
        else:
            hw = tg['highway']
            if hw == 'track' and tg.get('tracktype') not in (None, 'grade1', 'grade2'): continue  # pista dolenta: no
            pen = .35 if hw == 'track' else 0
            pts = e.get('geometry') or []
            if not pts: continue
            p = min(pts, key=lambda p: km(la, lo, p['lat'], p['lon'])); dkm = km(la, lo, p['lat'], p['lon'])
            nom = tg.get('name') or tg.get('ref') or ''
            kind = ('pista' if hw == 'track' else 'camí asfaltat' if hw == 'service' else 'carretera') + (f" {nom}" if nom else '')
            if hw == 'track' and tg.get('surface') in ('asphalt', 'paved', 'concrete'): kind += ' (asfaltada)'
            cand = (dkm + pen, p['lat'], p['lon'], kind, dkm)
        if best is None or cand[0] < best[0]: best = cand
    if not best: return None
    return dict(lat=best[1], lng=best[2], que=best[3], km=best[4])

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('lloc'); ap.add_argument('--sp', default='rov', choices=SP)
    ap.add_argument('--km', type=float, default=40); ap.add_argument('--dies'); ap.add_argument('--n', type=int, default=3); ap.add_argument('--json', action='store_true')
    a = ap.parse_args(); R = SP[a.sp]
    today = dt.date.today()
    dies = [dt.date.fromisoformat(x) for x in a.dies.split(',')] if a.dies else [today + dt.timedelta((5 - today.weekday()) % 7), today + dt.timedelta((5 - today.weekday()) % 7 + 1)]
    g = get('https://geocoding-api.open-meteo.com/v1/search?' + urllib.parse.urlencode(dict(name=a.lloc, count=10, language='ca', countryCode='ES')))
    res = [x for x in g.get('results', []) if x.get('admin1') in ('Catalunya', 'Cataluña', 'Catalonia')] or g.get('results', [])
    if not res: raise SystemExit(f'No trobo «{a.lloc}».')
    P = res[0]; la0, lo0 = P['latitude'], P['longitude']
    Z = [z for z in json.load(open(R['region'], encoding='utf-8'))['zones'] if z['ha'] >= 15 and km(la0, lo0, z['lat'], z['lng']) <= a.km]
    for z in Z: z['_t'] = terreny(z, a.sp); z['_km'] = km(la0, lo0, z['lat'], z['lng'])
    Z.sort(key=lambda z: -z['_t']); cand = []
    for z in Z:  # les 30 millors de terreny, separades almenys 3 km
        if all(km(z['lat'], z['lng'], c['lat'], c['lng']) > 3 for c in cand): cand.append(z)
        if len(cand) == 30: break
    if not cand: raise SystemExit(f"No hi ha boscos de {R['nom']} a {a.km:.0f} km de {P['name']}.")
    fd = max(1, (max(dies) - today).days + 1)
    for j in range(0, len(cand), 30):
        ch = cand[j:j + 30]
        u = ('https://api.open-meteo.com/v1/forecast?latitude=' + ','.join(f"{z['lat']:.4f}" for z in ch) + '&longitude=' + ','.join(f"{z['lng']:.4f}" for z in ch) +
             f'&daily=precipitation_sum,temperature_2m_mean,temperature_2m_min&past_days=50&forecast_days={min(16, fd + 1)}&timezone=Europe%2FMadrid')
        W = get(u); W = W if isinstance(W, list) else [W]
        for z, w in zip(ch, W):
            D = w['daily']; days = [dt.date.fromisoformat(x) for x in D['time']]
            wins, dl = avalua(R, a.sp, days, D['precipitation_sum'], D['temperature_2m_mean'], D['temperature_2m_min'], z['alt'], z['ob'], today)
            hit = [w_ for w_ in wins if any(w_['a'] <= d <= w_['b'] for d in dies)]
            z['_w'] = max(hit, key=lambda w_: w_['v']) if hit else None; z['_dl'] = dl
            z['_dies'] = [d for d in dies if z['_w'] and z['_w']['a'] <= d <= z['_w']['b']]
            z['_r15'] = sum(x or 0 for x in D['precipitation_sum'][max(0, days.index(today) - 14):days.index(today) + 1]) if today in days else None
    # nota final: la tanda manda; el terreny i la distància desempaten
    for z in cand: z['_n'] = (z['_w']['v'] if z['_w'] else -1) + 4 * z['_t'] - z['_km'] / 10
    top = sorted(cand, key=lambda z: -z['_n'])[:a.n]
    for z in top:
        b = bosc_real(z['lat'], z['lng'], a.sp)
        if b: z['lat'], z['lng'] = b
        z['_p'] = aparcar(z['lat'], z['lng']); z['_nom'] = lloc_nom(z['lat'], z['lng'])
        z['_reg'] = [t for (s, n_, w, e), t in REGULADES if s <= z['lat'] <= n_ and w <= z['lng'] <= e]
    if a.json:
        print(json.dumps([{k: (str(v) if isinstance(v, dt.date) else v) for k, v in z.items()} for z in top], default=str, ensure_ascii=False, indent=1)); return
    print(f"# {R['nom'].capitalize()} a prop de {P['name']} · {', '.join(fdia(d) for d in dies)}\n")
    if not any(z['_w'] for z in top): print(f"Cap bosc a {a.km:.0f} km té tanda aquests dies. Els millors de terreny, per si de cas:\n")
    for i, z in enumerate(top, 1):
        w = z['_w']; p = z['_p']
        nota = f"nota {w['v']}, tanda {'bona' if w['v'] >= 60 else 'normal' if w['v'] >= 35 else 'fluixa'}" if w else 'sense tanda aquests dies'
        print(f"## {i}. {z['_nom'] or 'Bosc'}: {z['ha']} ha de {z['arbre']} a {z['alt']} m · {nota}")
        print(f"A {z['_km']:.0f} km de {P['name']} en línia recta, cap al {rumb(la0, lo0, z['lat'], z['lng'])}.")
        if w:
            print(f"☔ {round(w['mm'])} litres a partir del {fdia(w['t1'])} · tanda del {fdia(w['a'])} al {fdia(w['b'])}, millor dia {fdia(w['peak'])}"
                  + (f" (+{z['_dl']} dies per l'altura)" if z['_dl'] else '') + (' · la temperatura encara pot canviar-ho' if w['prov'] else ''))
            print(f"   Hi cauen: {', '.join(fdia(d) for d in z['_dies'])}.")
        elif z['_r15'] is not None: print(f"☔ {round(z['_r15'])} litres els últims 15 dies.")
        if p:
            print(f"🅿️ Aparca: {p['que']} → {gmdir(p['lat'], p['lng'])}")
            print(f"🌲 Pentina: camina cap al {rumb(p['lat'], p['lng'], z['lat'], z['lng'])} ({p['km'] * 1000:.0f} m); el cor del bosc és aquí → {gm(z['lat'], z['lng'])}")
        else: print(f"🌲 El bosc: {gm(z['lat'], z['lng'])} (no he trobat on aparcar a OpenStreetMap)")
        print(f"   {round(z['ob'] * 100)}% cara nord · pendent mitjà {z.get('pend', '?')}°" + (f" · {round(z['emp'] * 100)}% massa costerut" if (z.get('emp') or 0) >= .15 else '')
              + (f" · terra {'calcària' if z.get('calc', 0) >= .5 else 'àcida' if z.get('acida', 0) >= .5 else 'barrejada'}" if a.sp == 'rov' else ''))
        for t in z['_reg']: print(f"⚠️ {t}")
        print()

if __name__ == '__main__':
    main()
