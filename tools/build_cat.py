"""Tota Catalunya: capes del mapa, dades per tocar el mapa i zones candidates, fet per trossos.

Per a cada tros (6×6 rajoles z12, uns 45 km, amb una rajola de marge per no deixar costures):
  - cara (nord/sud/pla) amb el relleu Terrarium, com abans;
  - coberta del sòl (ICGC 2023) i roca (ICGC 1:50.000) amb els WMS de l'ICGC;
  - altura i pendent amb el MDT25 de l'IGN.
Surt:
  tiles/cares/{z}/{x}/{y}.png i tiles/acid/... (z8-z12), com abans però per a tot el país;
  tiles/info/11/{x}/{y}.png: R = cara×28, G = roca×80, B = arbre×40 (per tocar el mapa sense baixar una imatge enorme);
  data/region.json (zones de ceps) i data/region_rov.json (zones de pinar), amb pendent.
Cal 1 h més o menys. Es pot tornar a executar: guarda els trossos fets a .cat_cache/ i no els torna a baixar."""
import io, json, math, os, re, shutil, subprocess, sys, time
import concurrent.futures as cf
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

S, N, W, E = 40.52, 42.87, 0.15, 3.34          # Catalunya
Z, B = 12, 6                                    # rajoles z12, trossos de 6×6 rajoles
CACHE = '.cat_cache'; os.makedirs(CACHE, exist_ok=True)
HOME = dict(nom='Torredembarra', lat=41.14616, lng=1.39595)

def tx(lon): return (lon + 180) / 360 * 2**Z
def ty(lat): return (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * 2**Z
def tlon(x): return x / 2**Z * 360 - 180
def tlat(y): return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / 2**Z))))
X0 = int(tx(W)) // 2 * 2; Y0 = int(ty(N)) // 2 * 2
X1 = X0 + math.ceil((int(tx(E)) + 1 - X0) / B) * B; Y1 = Y0 + math.ceil((int(ty(S)) + 1 - Y0) / B) * B   # exclusius
print('rajoles', X0, X1, Y0, Y1, 'trossos', (X1 - X0) // B, 'x', (Y1 - Y0) // B, flush=True)

def get(url, binary=True, tries=6):
    for k in range(tries):
        r = subprocess.run(['curl', '-sfL', '--max-time', '240', '-A', 'boletus-setup/1.0', url], capture_output=True)
        if not r.returncode and r.stdout: return r.stdout
        time.sleep(5 + 10 * k)
    raise RuntimeError(url)

# ---------- classes per color (WMS), amb memòria entre trossos ----------
COB = "https://geoserveis.icgc.cat/servei/catalunya/cobertes-sol/wms"
GEO = "https://geoserveis.icgc.cat/servei/catalunya/geologia-territorial/wms"
CLS = json.load(open(f'{CACHE}/classes.json')) if os.path.exists(f'{CACHE}/classes.json') else {}
CLS = {k: v for k, v in CLS.items() if k.startswith('cobertes_2023:')}   # la coberta sí que té un color per classe
# El mapa geològic, en canvi, fa servir el mateix color per a roques diferents segons la zona: el text de cada color
# es guarda per tros (TXT) i la roca es decideix després (així es poden canviar les regles sense tornar a preguntar)
TXT = json.load(open(f'{CACHE}/geo_txt.json', encoding='utf-8')) if os.path.exists(f'{CACHE}/geo_txt.json') else {}
def m3857(lon, lat): return lon * 20037508.34 / 180, math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * 6378137
def wms(base, layer, bb, w, h):
    u = (f"{base}?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS={layer}&STYLES=&CRS=EPSG:3857"
         f"&BBOX={bb[0]},{bb[1]},{bb[2]},{bb[3]}&WIDTH={w}&HEIGHT={h}&FORMAT=image/png")
    return np.asarray(Image.open(io.BytesIO(get(u))).convert('RGB'))
def pcov(t):
    m = re.search(r"class = '(.*)'", t); return re.sub(r'^[\d.]+\s*\(\d+\)\s*', '', m.group(1)) if m else ''
def pgeo(t):
    """Descripció | era | període de la unitat (o el text buit si no n'hi ha)."""
    parts = t.split(';')
    if 'Descripcio_protolit' not in parts: return ''
    n = parts.index('Descripcio_protolit') + 1
    return '|'.join(parts[n + k].strip() for k in (3, 5, 6)) if len(parts) > n + 6 else ''
def treecode(n):
    if re.search(r'aciculifolis', n): return 1          # pinar
    if re.search(r'esclerofil', n): return 2            # alzinar / surera
    if re.search(r'caducifolis', n): return 3           # roureda
    if re.search(r'Matollar', n): return 4              # matollar
    if re.search(r'Altres conreus llenyosos', n): return 5  # avellaners
    return 0
ACID = re.compile(r"granit|granodior|pissarr|esquist|gres|quars|pòrfir|porfir|lidit|corneana|pelit|leucogran|aplit|filit|grauvac|licorell", re.I)
# gresos i conglomerats del Terciari i del Quaternari (plana de Lleida, Depressió Central): ciment calcari, no són àcids
HARD = re.compile(r"granit|granodior|pissarr|esquist|pòrfir|porfir|lidit|corneana|leucogran|aplit|filit|grauvac|licorell", re.I)
BASIC = re.compile(r"calc|dolom|marg|guix|carbonat", re.I)
def rockcode(t):
    if not t: return 0
    d, era, per = (t.split('|') + ['', ''])[:3]
    jove = 'Cenozoic' in era or per in ('Quaternari', 'Neogen', 'Paleogen')
    a = bool(HARD.search(d)) if jove else bool(ACID.search(d))
    b = bool(BASIC.search(d))
    return 3 if a and b else 1 if a else 2 if b else 0
def classify(img, base, layer, bb, parse, code, minpx, tros=None):
    """Cada color vol dir una classe: es pregunta (GetFeatureInfo) i es recorda. La geologia, per tros."""
    h, w, _ = img.shape
    key = (img[..., 0].astype(np.int32) << 16) | (img[..., 1].astype(np.int32) << 8) | img[..., 2]
    cols, inv, cnt = np.unique(key.ravel(), return_inverse=True, return_counts=True)
    inv = inv.reshape(h, w); out = np.zeros(len(cols), np.uint8); ask = []
    for i, c in enumerate(cols):
        if c in (0xFFFFFF, 0): continue          # blanc o transparent: mar o fora del mapa
        if tros:
            k = f'{tros}:{int(c)}'
            if k in TXT: out[i] = code(TXT[k])
            elif cnt[i] >= minpx: ask.append(i)
            continue
        k = f'{layer}:{int(c)}'
        if k in CLS: out[i] = CLS[k]
        elif cnt[i] >= minpx: ask.append(i)
    def info(i):
        ys, xs = np.nonzero(inv == i); j = len(ys) // 2
        u = (f"{base}?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetFeatureInfo&LAYERS={layer}&QUERY_LAYERS={layer}&CRS=EPSG:3857"
             f"&BBOX={bb[0]},{bb[1]},{bb[2]},{bb[3]}&WIDTH={w}&HEIGHT={h}&I={int(xs[j])}&J={int(ys[j])}&INFO_FORMAT=text/plain&STYLES=")
        try: return i, parse(get(u, tries=3).decode('utf-8', 'ignore'))
        except Exception: return i, None
    with cf.ThreadPoolExecutor(8) as ex:
        for i, t in ex.map(info, ask):
            if t is None: continue
            if tros: TXT[f'{tros}:{int(cols[i])}'] = t; out[i] = code(t)
            else: CLS[f'{layer}:{int(cols[i])}'] = int(code(t)); out[i] = code(t)
    return out[inv]

# ---------- un tros ----------
def terrarium(xa, xb, ya, yb):
    dem = np.zeros(((yb - ya) * 256, (xb - xa) * 256), np.float32)
    def t(xy):
        x, y = xy
        a = np.asarray(Image.open(io.BytesIO(get(f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{Z}/{x}/{y}.png"))).convert('RGB'), np.float32)
        return xy, a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768
    with cf.ThreadPoolExecutor(12) as ex:
        for (x, y), a in ex.map(t, [(x, y) for x in range(xa, xb) for y in range(ya, yb)]):
            dem[(y - ya) * 256:(y - ya + 1) * 256, (x - xa) * 256:(x - xa + 1) * 256] = a
    return dem
def mdt25(s, n, w, e):
    """MDT25 de l'IGN en 2×2 peces (fila 0 = nord)."""
    las = np.linspace(s, n, 3); los = np.linspace(w, e, 3); P = {}
    for i in range(2):
        for j in range(2):
            u = ('https://servicios.idee.es/wcs-inspire/mdt?SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverage&COVERAGEID=Elevacion4258_25'
                 f'&SUBSET=Lat({las[i]},{las[i+1]})&SUBSET=Long({los[j]},{los[j+1]})&FORMAT=image/tiff')
            try: P[(i, j)] = np.asarray(Image.open(io.BytesIO(get(u, tries=4))), np.float32)
            except Exception: P[(i, j)] = None
    ok = [a for a in P.values() if a is not None]
    if not ok: return None
    h = min(a.shape[0] for a in ok); w_ = min(a.shape[1] for a in ok)
    rows = [np.hstack([P[(i, j)][:h, :w_] if P[(i, j)] is not None else np.full((h, w_), -9999, np.float32) for j in range(2)]) for i in reversed(range(2))]
    d = np.vstack(rows); d[d < -100] = np.nan
    return d

def block(bx, by):
    f = f'{CACHE}/b_{bx}_{by}.npz'
    if os.path.exists(f): return dict(np.load(f))
    xa, xb, ya, yb = bx - 1, bx + B + 1, by - 1, by + B + 1          # amb marge
    Wp, Hp = (xb - xa) * 256, (yb - ya) * 256
    lo0, lo1, la1, la0 = tlon(xa), tlon(xb), tlat(ya), tlat(yb)
    (mx0, my0), (mx1, my1) = m3857(lo0, la0), m3857(lo1, la1)
    bb = (mx0, my0, mx1, my1)
    # relleu i cara (igual que build_region.py)
    fr = f'{CACHE}/raw_{bx}_{by}.npz'
    if os.path.exists(fr):
        R_ = np.load(fr); dem, cob, geo = R_['dem'], R_['cob'], R_['geo']; d = R_['mdt'] if R_['mdt'].size > 1 else None
    else:
        dem = terrarium(xa, xb, ya, yb)
        cob = wms(COB, 'cobertes_2023', bb, Wp, Hp); geo = wms(GEO, 'unitats-geologiques-50000', bb, Wp, Hp)
        d = mdt25(tlat(by + B) - .004, tlat(by) + .004, tlon(bx) - .005, tlon(bx + B) + .005)
        np.savez_compressed(fr, dem=dem, cob=cob, geo=geo, mdt=d if d is not None else np.zeros(1, np.float32))
    px = 40075016.686 * math.cos(math.radians((la0 + la1) / 2)) / 2**Z / 256
    k = np.array([1, 4, 6, 4, 1], np.float32); k /= k.sum()
    es = ndimage.convolve1d(ndimage.convolve1d(dem, k, axis=0), k, axis=1)
    p = np.pad(es, 1, mode='edge')
    dzdx = ((p[:-2, 2:] + 2 * p[1:-1, 2:] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[1:-1, :-2] + p[2:, :-2])) / (8 * px)
    dzdy = ((p[2:, :-2] + 2 * p[2:, 1:-1] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[:-2, 1:-1] + p[:-2, 2:])) / (8 * px)
    slope = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
    sec = (np.round(((np.degrees(np.arctan2(-dzdx, dzdy)) + 360) % 360) / 45).astype(np.int16) % 8).astype(np.uint8)
    sec[slope < 4] = 8
    # coberta i roca
    tree = classify(cob, COB, 'cobertes_2023', bb, pcov, treecode, 300)
    rock = classify(geo, GEO, 'unitats-geologiques-50000', bb, pgeo, rockcode, 150, tros=f'{bx}_{by}')
    json.dump(CLS, open(f'{CACHE}/classes.json', 'w')); json.dump(TXT, open(f'{CACHE}/geo_txt.json', 'w', encoding='utf-8'), ensure_ascii=False)
    # "altres conreus llenyosos" són avellaners només al Camp de Tarragona i voltants; a la resta (Lleida...) són fruiters
    yy_, xx_ = np.mgrid[0:Hp, 0:Wp]
    lat_ = np.degrees(np.arctan(np.sinh(math.pi * (1 - 2 * (ya + yy_ / 256) / 2**Z)))); lon_ = (xa + xx_ / 256) / 2**Z * 360 - 180
    tree[(tree == 5) & ~((lat_ > 40.95) & (lat_ < 41.45) & (lon_ > 0.70) & (lon_ < 1.50))] = 0
    del yy_, xx_, lat_, lon_
    # El mapa geològic porta dibuixats els noms de les unitats i les línies de contacte: aquests píxels no són
    # cap roca. S'omplen amb la roca del costat (només si en tenen una a 6 px o menys; el mar i França queden buits).
    for a_ in (rock, tree):
        z0 = a_ == 0
        if z0.any() and (~z0).any():
            dz, (iy, ix) = ndimage.distance_transform_edt(z0, return_indices=True)
            m = z0 & (dz <= 6); a_[m] = a_[iy[m], ix[m]]
    # capes de colors (amb el marge, i després es retalla)
    veg = tree > 0
    soft = lambda m, r=1.2: np.asarray(Image.fromarray((m * 255).astype(np.uint8), 'L').filter(ImageFilter.GaussianBlur(r)))
    a_ = soft(veg & np.isin(sec, [7, 0, 1])); b_ = soft(veg & np.isin(sec, [3, 4, 5]))
    cares = np.zeros((Hp, Wp, 4), np.uint8)
    cares[(a_ > 127) & (a_ >= b_)] = [52, 104, 200, 150]
    cares[(b_ > 127) & (b_ > a_)] = [232, 132, 48, 135]
    acid = ndimage.binary_opening((rock == 1) | (rock == 3), iterations=2)
    calc = ndimage.binary_opening(rock == 2, iterations=2) & ~acid
    edge = acid & ~ndimage.binary_erosion(acid, iterations=6)
    acl = np.zeros((Hp, Wp, 4), np.uint8); acl[calc] = [238, 234, 226, 165]; acl[edge] = [110, 45, 150, 240]
    core = (slice(256, -256), slice(256, -256))
    # mitja resolució (z11) per a les zones i per tocar el mapa
    hs = lambda a: a[core][::2, ::2]
    gh, gw = B * 128, B * 128
    # altura i pendent del MDT25, fets mitjana a cada cel·la de mitja resolució
    gs, gn_, gw_, ge = tlat(by + B), tlat(by), tlon(bx), tlon(bx + B)
    el = np.full((gh, gw), np.nan, np.float32); slm = np.full((gh, gw), np.nan, np.float32); sls = np.full((gh, gw), np.nan, np.float32)
    if d is not None:
        S2, N2, W2, E2 = gs - .004, gn_ + .004, gw_ - .005, ge + .005
        H_, W_ = d.shape
        dyy = (N2 - S2) * 111320 / H_; dxx = (E2 - W2) * 111320 * math.cos(math.radians((S2 + N2) / 2)) / W_
        dd = np.nan_to_num(d, nan=0)
        q = np.pad(ndimage.gaussian_filter(dd, .7), 1, mode='edge')
        sl = np.degrees(np.arctan(np.hypot(((q[:-2, 2:] + 2 * q[1:-1, 2:] + q[2:, 2:]) - (q[:-2, :-2] + 2 * q[1:-1, :-2] + q[2:, :-2])) / (8 * dxx),
                                           ((q[2:, :-2] + 2 * q[2:, 1:-1] + q[2:, 2:]) - (q[:-2, :-2] + 2 * q[:-2, 1:-1] + q[:-2, 2:])) / (8 * dyy))))
        valid = ~np.isnan(d)
        my = lambda la: math.log(math.tan(math.pi / 4 + math.radians(la) / 2))
        yy = my(gn_) - (my(gn_) - my(gs)) * (np.arange(gh + 1)) / gh
        latb = np.degrees(2 * np.arctan(np.exp(yy)) - math.pi / 2)
        lonb = gw_ + (ge - gw_) * np.arange(gw + 1) / gw
        rb = np.clip(((N2 - latb) / (N2 - S2) * H_).astype(int), 0, H_); cb = np.clip(((lonb - W2) / (E2 - W2) * W_).astype(int), 0, W_)
        r0, r1 = rb[:-1][:, None], np.minimum(np.maximum(rb[1:], rb[:-1] + 1), H_)[:, None]
        c0, c1 = cb[:-1][None, :], np.minimum(np.maximum(cb[1:], cb[:-1] + 1), W_)[None, :]
        def box(A):
            T = np.pad(A.astype(np.float64).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
            return T[r1, c1] - T[r0, c1] - T[r1, c0] + T[r0, c0]
        nv = box(valid)
        with np.errstate(invalid='ignore', divide='ignore'):
            el = (box(np.where(valid, dd, 0)) / nv).astype(np.float32)
            slm = (box(np.where(valid, sl, 0)) / nv).astype(np.float32)
            sls = (box(valid & (sl > 25)) / nv).astype(np.float32)
    out = dict(cares=cares[core], acid=acl[core], sec=hs(sec), rock=hs(rock), tree=hs(tree), el=el, slm=slm, sls=sls)
    np.savez_compressed(f, **out)
    return out

# ---------- tots els trossos ----------
GW, GH = (X1 - X0) * 128, (Y1 - Y0) * 128
G = dict(sec=np.full((GH, GW), 8, np.uint8), rock=np.zeros((GH, GW), np.uint8), tree=np.zeros((GH, GW), np.uint8),
         el=np.full((GH, GW), np.nan, np.float32), slm=np.full((GH, GW), np.nan, np.float32), sls=np.full((GH, GW), np.nan, np.float32))
TR = 'tiles_new'  # es fan a part i al final substitueixen les d'ara
shutil.rmtree(TR, ignore_errors=True)
def save_tile(layer, z, x, y, im):
    d = f'{TR}/{layer}/{z}/{x}'; os.makedirs(d, exist_ok=True); im.save(f'{d}/{y}.png', optimize=True)
blocks = [(bx, by) for by in range(Y0, Y1, B) for bx in range(X0, X1, B)]
if '--un' in sys.argv:  # prova: només el tros d'un punt (lat, lon)
    la, lo = map(float, sys.argv[sys.argv.index('--un') + 1:sys.argv.index('--un') + 3])
    bx = X0 + (int(tx(lo)) - X0) // B * B; by = Y0 + (int(ty(la)) - Y0) // B * B
    o = block(bx, by)
    bg = Image.new('RGBA', o['cares'].shape[1::-1], (60, 70, 60, 255)); bg.alpha_composite(Image.fromarray(o['cares'])); bg.alpha_composite(Image.fromarray(o['acid']))
    bg.convert('RGB').resize((768, 768)).save('../prova_bloc.png'); print('tros', bx, by, 'classes', len(CLS)); sys.exit()
for n, (bx, by) in enumerate(blocks, 1):
    t0 = time.time(); o = block(bx, by)
    for layer in ['cares', 'acid']:
        a = o[layer]
        for j in range(B):
            for i in range(B):
                t = a[j * 256:(j + 1) * 256, i * 256:(i + 1) * 256]
                if t[..., 3].any(): save_tile(layer, Z, bx + i, by + j, Image.fromarray(t, 'RGBA'))
    oy, ox = (by - Y0) * 128, (bx - X0) * 128
    for k in G: G[k][oy:oy + B * 128, ox:ox + B * 128] = o[k]
    print(f'tros {n}/{len(blocks)} ({bx},{by}) {time.time() - t0:.0f} s', flush=True)

# ---------- rajoles de menys zoom (z11-z8) a partir de les de z12 ----------
for layer in ['cares', 'acid']:
    for z in range(Z - 1, 7, -1):
        src = f'{TR}/{layer}/{z + 1}'
        if not os.path.isdir(src): continue
        parents = {(int(x) // 2, int(y[:-4]) // 2) for x in os.listdir(src) for y in os.listdir(f'{src}/{x}')}
        for (x, y) in parents:
            big = Image.new('RGBA', (512, 512))
            for dx in range(2):
                for dy in range(2):
                    fp = f'{src}/{2 * x + dx}/{2 * y + dy}.png'
                    if os.path.exists(fp): big.paste(Image.open(fp).convert('RGBA'), (dx * 256, dy * 256))
            save_tile(layer, z, x, y, big.resize((256, 256), Image.LANCZOS))
    print(layer, sum(len(fs) for _, _, fs in os.walk(f'{TR}/{layer}')), 'rajoles', flush=True)

# ---------- dades per tocar el mapa: rajoles z11 ----------
info = np.stack([G['sec'] * 28, G['rock'] * 80, G['tree'] * 40], -1).astype(np.uint8)
n_info = 0
for j in range(GH // 256):
    for i in range(GW // 256):
        sl = (slice(j * 256, (j + 1) * 256), slice(i * 256, (i + 1) * 256))
        if not (G['tree'][sl].any() or G['rock'][sl].any()): continue     # fora de Catalunya o mar
        save_tile('info', 11, X0 // 2 + i, Y0 // 2 + j, Image.fromarray(np.ascontiguousarray(info[sl]), 'RGB')); n_info += 1
print('info', n_info, 'rajoles', flush=True)

# ---------- zones ----------
bounds = [[tlat(Y1), tlon(X0)], [tlat(Y0), tlon(X1)]]
my = lambda la: math.log(math.tan(math.pi / 4 + math.radians(la) / 2))
ys = my(bounds[1][0]) - (my(bounds[1][0]) - my(bounds[0][0])) * (np.arange(GH) + .5) / GH
glat = np.degrees(2 * np.arctan(np.exp(ys)) - math.pi / 2); glon = bounds[0][1] + (bounds[1][1] - bounds[0][1]) * (np.arange(GW) + .5) / GW
cell_m = 40075016.686 * math.cos(math.radians(41.6)) / 2**11 / 256; cell_ha = cell_m ** 2 / 1e4
TREES = ['', 'pinar', 'alzinar', 'roureda', 'matollar', 'avellaners']
el = np.nan_to_num(G['el'], nan=-999)
def zones(cand, extra):
    cand = ndimage.binary_opening(cand, iterations=1)
    lab, nl = ndimage.label(cand, structure=np.ones((3, 3)))
    area = ndimage.sum(np.ones_like(lab), lab, np.arange(1, nl + 1)) * cell_ha
    big = np.isin(lab, np.nonzero(area > 600)[0] + 1)
    kk = max(1, round(2500 / cell_m)); yy, xx = np.mgrid[0:GH, 0:GW]
    cellid = (yy // kk) * (GW // kk + 1) + (xx // kk) + 1
    lab2 = np.where(big, 0, lab); nxt = nl + 1
    for cid in np.unique(cellid[big]):
        m = big & (cellid == cid); l, nn = ndimage.label(m, structure=np.ones((3, 3))); lab2[m] = l[m] + nxt - 1; nxt += nn
    out = []
    for L, sl in enumerate(ndimage.find_objects(lab2), 1):
        if sl is None: continue
        m = lab2[sl] == L; nc = int(m.sum())
        if nc * cell_ha < 15: continue          # l'app només fa servir zones de 15 ha o més
        s_, t_, e_, r_ = G['sec'][sl][m], G['tree'][sl][m], el[sl][m], G['rock'][sl][m]
        y_, x_ = np.nonzero(m); j = np.argmin((y_ - y_.mean()) ** 2 + (x_ - x_.mean()) ** 2)
        y, x = y_[j] + sl[0].start, x_[j] + sl[1].start
        tc = np.bincount(t_, minlength=6)
        z = dict(lat=round(float(glat[y]), 5), lng=round(float(glon[x]), 5), ha=round(nc * cell_ha),
                 ob=round(float(np.isin(s_, [7, 0, 1]).mean()), 2), so=round(float(np.isin(s_, [3, 4, 5]).mean()), 2),
                 alt=int(np.median(e_)), arbre=TREES[int(tc[1:].argmax()) + 1],
                 bo=round(float((tc[2] + tc[3] + tc[5]) / nc), 2), acida=round(float((r_ == 1).mean()), 2),
                 pend=int(round(float(np.nanmean(G['slm'][sl][m])))) if np.isfinite(G['slm'][sl][m]).any() else 0,
                 emp=round(float(np.nanmean(G['sls'][sl][m])), 2) if np.isfinite(G['sls'][sl][m]).any() else 0)
        if extra: z.update(pinar=round(float((t_ == 1).mean()), 2), calc=round(float((r_ == 2).mean()), 2))
        out.append(z)
    out.sort(key=lambda z: -z['ha'])
    return out
for fn, cand, alt, extra in [('data/region.json', (G['tree'] > 0) & ((G['rock'] == 1) | (G['rock'] == 3)) & (el >= 200) & (el <= 800), [200, 800], False),
                             ('data/region_rov.json', (G['tree'] == 1) & (el >= 100) & (el <= 1200), [100, 1200], True)]:
    zs = zones(cand, extra)
    json.dump(dict(bounds=bounds, home=HOME, criteris=dict(alt=alt, min_ha=15, quadre_km=2.5, tot_catalunya=True), zones=zs),
              open(fn, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print(fn, len(zs), 'zones', os.path.getsize(fn) // 1024, 'KB', flush=True)
Image.fromarray(np.ascontiguousarray(info[::8, ::8])).save(f'{CACHE}/preview_info.png')
for name in ['cares', 'acid', 'info']:
    shutil.rmtree(f'tiles/{name}', ignore_errors=True)
    if os.path.isdir(f'{TR}/{name}'): shutil.move(f'{TR}/{name}', f'tiles/{name}')
shutil.rmtree(TR, ignore_errors=True)
print('fet', flush=True)
