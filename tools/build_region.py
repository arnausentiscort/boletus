"""Boscos candidats en un radi de ~50 km de Torredembarra.

Per a cada punt (~29 m): orientació (relleu Terrarium), coberta del sòl (ICGC 2023) i roca (ICGC 1:50.000).
Un punt és candidat si hi ha bosc, matollar o avellaners, la roca és àcida o barrejada i és entre 200 i 800 m.
Surt: data/region.png (candidats pintats per obaga/solana) i data/region.json (zones agrupades)."""
import io, json, math, re, subprocess, sys, concurrent.futures as cf
import numpy as np
from PIL import Image
from scipy import ndimage

OUT = 'data'
LAT, LON, R_KM = 41.14616, 1.39595, 52
dlat = R_KM / 111.32; dlon = R_KM / (111.32 * math.cos(math.radians(LAT)))
S, N, W, E = LAT - dlat, LAT + dlat, LON - dlon, LON + dlon
Z = 12

def get(url):
    for _ in range(4):
        r = subprocess.run(["curl", "-sfL", "--max-time", "120", url], capture_output=True)
        if not r.returncode: return r.stdout
    raise RuntimeError(url)
def tx(lon): return (lon + 180) / 360 * 2**Z
def ty(lat): return (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * 2**Z
def tlon(x): return x / 2**Z * 360 - 180
def tlat(y): return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / 2**Z))))

X0, X1, Y0, Y1 = int(tx(W)), int(tx(E)), int(ty(N)), int(ty(S))
Wp, Hp = (X1 - X0 + 1) * 256, (Y1 - Y0 + 1) * 256
bounds = [[tlat(Y1 + 1), tlon(X0)], [tlat(Y0), tlon(X1 + 1)]]
print('mida', Wp, Hp, bounds, flush=True)

# --- Relleu ---
dem = np.zeros((Hp, Wp), np.float32)
def tile(xy):
    x, y = xy
    a = np.asarray(Image.open(io.BytesIO(get(f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{Z}/{x}/{y}.png"))).convert('RGB'), np.float32)
    return xy, a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768
with cf.ThreadPoolExecutor(12) as ex:
    for (x, y), a in ex.map(tile, [(x, y) for x in range(X0, X1 + 1) for y in range(Y0, Y1 + 1)]):
        dem[(y - Y0) * 256:(y - Y0 + 1) * 256, (x - X0) * 256:(x - X0 + 1) * 256] = a
px = 40075016.686 * math.cos(math.radians(LAT)) / 2**Z / 256
k = np.array([1, 4, 6, 4, 1], np.float32); k /= k.sum()
es = ndimage.convolve1d(ndimage.convolve1d(dem, k, axis=0), k, axis=1)
p = np.pad(es, 1, mode='edge')
a_, b_, c_ = p[:-2, :-2], p[:-2, 1:-1], p[:-2, 2:]
d_, f_ = p[1:-1, :-2], p[1:-1, 2:]
g_, h_, i_ = p[2:, :-2], p[2:, 1:-1], p[2:, 2:]
dzdx = ((c_ + 2 * f_ + i_) - (a_ + 2 * d_ + g_)) / (8 * px)
dzdy = ((g_ + 2 * h_ + i_) - (a_ + 2 * b_ + c_)) / (8 * px)
slope = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
sec = (np.round(((np.degrees(np.arctan2(-dzdx, dzdy)) + 360) % 360) / 45).astype(np.int8) % 8)
sec[slope < 4] = 8
print('relleu fet', flush=True)

# --- WMS de l'ICGC al mateix encuadre, i classes per color ---
def m3857(lon, lat): return lon * 20037508.34 / 180, math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * 6378137
(bx0, by0), (bx1, by1) = m3857(bounds[0][1], bounds[0][0]), m3857(bounds[1][1], bounds[1][0])
def wms_rgb(base, layer):
    img = np.zeros((Hp, Wp, 3), np.uint8)
    nx, ny = math.ceil(Wp / 2048), math.ceil(Hp / 2048)
    for iy in range(ny):
        for ix in range(nx):
            x0, x1 = ix * Wp // nx, (ix + 1) * Wp // nx
            y0, y1 = iy * Hp // ny, (iy + 1) * Hp // ny
            mx0 = bx0 + (bx1 - bx0) * x0 / Wp; mx1 = bx0 + (bx1 - bx0) * x1 / Wp
            my1 = by1 - (by1 - by0) * y0 / Hp; my0 = by1 - (by1 - by0) * y1 / Hp
            u = (f"{base}?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS={layer}&STYLES=&CRS=EPSG:3857"
                 f"&BBOX={mx0},{my0},{mx1},{my1}&WIDTH={x1-x0}&HEIGHT={y1-y0}&FORMAT=image/png")
            img[y0:y1, x0:x1] = np.asarray(Image.open(io.BytesIO(get(u))).convert('RGB'))
    return img
def classify(base, layer, img, parse, minpx=300):
    cols, inv, cnt = np.unique(img.reshape(-1, 3), axis=0, return_inverse=True, return_counts=True)
    inv = inv.reshape(Hp, Wp)
    big = [i for i in np.argsort(-cnt) if cnt[i] >= minpx]
    def info(i):
        ys, xs = np.nonzero(inv == i); j = len(ys) // 2; y, x = int(ys[j]), int(xs[j])
        u = (f"{base}?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetFeatureInfo&LAYERS={layer}&QUERY_LAYERS={layer}&CRS=EPSG:3857"
             f"&BBOX={bx0},{by0},{bx1},{by1}&WIDTH={Wp}&HEIGHT={Hp}&I={x}&J={y}&INFO_FORMAT=text/plain&STYLES=")
        try: return i, parse(get(u).decode('utf-8', 'ignore'))
        except Exception: return i, None
    out = {}
    with cf.ThreadPoolExecutor(8) as ex:
        for i, v in ex.map(info, big): out[int(i)] = v
    return inv, out

COB = "https://geoserveis.icgc.cat/servei/catalunya/cobertes-sol/wms"
cimg = wms_rgb(COB, 'cobertes_2023')
def pcov(t):
    m = re.search(r"class = '(.*)'", t); return re.sub(r'^[\d.]+\s*\(\d+\)\s*', '', m.group(1)) if m else None
cinv, cnames = classify(COB, 'cobertes_2023', cimg, pcov)
def treecode(n):
    if not n: return 0
    if re.search(r'aciculifolis', n): return 1          # pinar
    if re.search(r'esclerofil', n): return 2            # alzinar / surera
    if re.search(r'caducifolis', n): return 3           # roureda
    if re.search(r'Matollar', n): return 4              # matollar
    if re.search(r'Altres conreus llenyosos', n): return 5  # avellaners
    return 0
tree = np.zeros((Hp, Wp), np.uint8)
for i, n in cnames.items(): tree[cinv == i] = treecode(n)
print('cobertes:', sorted({n for n in cnames.values() if n}), flush=True)

GEO = "https://geoserveis.icgc.cat/servei/catalunya/geologia-territorial/wms"
gimg = wms_rgb(GEO, 'unitats-geologiques-50000')
def pgeo(t):
    parts = t.split(';')
    if 'Descripcio_protolit' not in parts: return None
    n = parts.index('Descripcio_protolit') + 1
    return parts[n + 3].strip() if len(parts) > n + 3 else None
ginv, gnames = classify(GEO, 'unitats-geologiques-50000', gimg, pgeo, minpx=150)
ACID = re.compile(r"granit|granodior|pissarr|esquist|gres|quars|pòrfir|porfir|lidit|corneana|pelit|leucogran|aplit|filit|grauvac|licorell", re.I)
BASIC = re.compile(r"calc|dolom|marg|guix|carbonat", re.I)
rock = np.zeros((Hp, Wp), np.uint8)  # 1 àcida, 2 calcària, 3 barrejada
for i, d in gnames.items():
    if not d: continue
    a, b = bool(ACID.search(d)), bool(BASIC.search(d))
    rock[ginv == i] = 3 if a and b else 1 if a else 2 if b else 0
print('roques àcides:', len([d for d in gnames.values() if d and ACID.search(d)]), flush=True)

# --- Candidats ---
cand = (tree > 0) & ((rock == 1) | (rock == 3)) & (es >= 200) & (es <= 800)
lab, nlab = ndimage.label(ndimage.binary_opening(cand, iterations=1), structure=np.ones((3, 3)))
cell_ha = px * px / 1e4
idx = np.arange(1, nlab + 1)
area = ndimage.sum(np.ones_like(lab), lab, idx) * cell_ha
keep = idx[area >= 8]
print('zones', nlab, 'grans', len(keep), flush=True)
TREES = ['', 'pinar', 'alzinar', 'roureda', 'matollar', 'avellaners']
objs = ndimage.find_objects(lab)
zones = []
def ll(y, x):
    my = math.log(math.tan(math.pi / 4 + math.radians(bounds[1][0]) / 2)) - (y / Hp) * (math.log(math.tan(math.pi / 4 + math.radians(bounds[1][0]) / 2)) - math.log(math.tan(math.pi / 4 + math.radians(bounds[0][0]) / 2)))
    return math.degrees(2 * math.atan(math.exp(my)) - math.pi / 2), bounds[0][1] + (bounds[1][1] - bounds[0][1]) * x / Wp
for L in keep:
    sl = objs[L - 1]; m = lab[sl] == L
    s_ = sec[sl][m]; t_ = tree[sl][m]; e_ = es[sl][m]; r_ = rock[sl][m]
    ys, xs = np.nonzero(m); cy, cx = ys.mean() + sl[0].start, xs.mean() + sl[1].start
    # punt de la zona més proper al centre (perquè l'agulla caigui dins)
    j = np.argmin((ys + sl[0].start - cy) ** 2 + (xs + sl[1].start - cx) ** 2)
    lat, lon = ll(ys[j] + sl[0].start + .5, xs[j] + sl[1].start + .5)
    n_ = len(s_)
    ob = float(np.isin(s_, [7, 0, 1]).sum() / n_); so = float(np.isin(s_, [3, 4, 5]).sum() / n_)
    tc = np.bincount(t_, minlength=6)
    zones.append(dict(lat=round(lat, 5), lng=round(lon, 5), ha=round(float(n_ * cell_ha)), ob=round(ob, 2), so=round(so, 2),
                      alt=int(np.median(e_)), arbre=TREES[int(tc[1:].argmax()) + 1],
                      bo=round(float((tc[2] + tc[3] + tc[5]) / n_), 2), acida=round(float((r_ == 1).sum() / n_), 2)))
zones.sort(key=lambda z: -z['ha'])

# --- Capa del mapa: candidats pintats per cara ---
cl = np.zeros((Hp, Wp), np.uint8)
good = np.isin(lab, keep)
cl[good] = 3
cl[good & np.isin(sec, [7, 0, 1])] = 1
cl[good & np.isin(sec, [3, 4, 5])] = 2
img = Image.fromarray(cl, 'P')
img.putpalette([0, 0, 0, 52, 104, 200, 232, 132, 48, 236, 206, 70] + [0] * 756)
img.info['transparency'] = bytes([0, 200, 190, 170] + [0] * 252)
img.save(f'{OUT}/region.png', optimize=True, transparency=bytes([0, 200, 190, 170] + [0] * 252))
json.dump(dict(bounds=bounds, home=dict(nom='Torredembarra', lat=LAT, lng=LON), criteris=dict(alt=[200, 800], min_ha=8),
               zones=zones), open(f'{OUT}/region.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print('fet:', len(zones), 'zones', flush=True)
