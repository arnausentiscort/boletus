"""Torna a fer les zones de data/region.json a partir de data/reg_info.png i del relleu MDT25 de l'IGN.

Una zona és un tros seguit de bosc, matollar o avellaners sobre terra àcida, entre 200 i 800 m.
Les zones grans (les serres de Prades i dels voltants surten com un sol tros de milers d'hectàrees)
es parteixen en quadres de 2,5 km, perquè cada tros tingui el seu punt i les seves dades.
Per a cada zona: mida, cares, altura, arbre, terra i pendent (pend = mitjà en graus, emp = part amb més de 25°).
S'ha d'executar després de build_region.py."""
import io, json, math, os, subprocess, tempfile
import concurrent.futures as cf
import numpy as np
from PIL import Image
from scipy import ndimage

R = json.load(open('data/region.json', encoding='utf-8'))
(S, W), (N, E) = R['bounds']
STEEP, CELL_KM, BIG_HA, MIN_HA = 25, 2.5, 600, 8

def get(url):
    for _ in range(4):
        r = subprocess.run(['curl', '-sfL', '--max-time', '180', url], capture_output=True)
        if not r.returncode: return r.stdout
    raise RuntimeError(url)

# --- Relleu de 25 m en trossos (es desa a la carpeta temporal per no baixar-lo cada cop) ---
cache = os.path.join(tempfile.gettempdir(), 'boletus_mdt25.npy')
if os.path.exists(cache):
    dem = np.load(cache)
else:
    NY, NX = 4, 5
    lats = np.linspace(S, N, NY + 1); lons = np.linspace(W, E, NX + 1)
    def chunk(ij):
        i, j = ij
        u = ('https://servicios.idee.es/wcs-inspire/mdt?SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverage'
             f'&COVERAGEID=Elevacion4258_25&SUBSET=Lat({lats[i]},{lats[i+1]})&SUBSET=Long({lons[j]},{lons[j+1]})&FORMAT=image/tiff')
        return ij, np.asarray(Image.open(io.BytesIO(get(u))), np.float32)
    parts = {}
    with cf.ThreadPoolExecutor(4) as ex:
        for ij, a in ex.map(chunk, [(i, j) for i in range(NY) for j in range(NX)]): parts[ij] = a
    # cada tros pot tenir una mida lleugerament diferent: s'igualen abans d'enganxar-los
    h = min(a.shape[0] for a in parts.values()); w = min(a.shape[1] for a in parts.values())
    dem = np.vstack([np.hstack([parts[(i, j)][:h, :w] for j in range(NX)]) for i in reversed(range(NY))])  # fila 0 = nord
    dem[dem < -100] = 0  # mar i sense dades
    np.save(cache, dem)
H_, W_ = dem.shape
dy = (N - S) * 111320 / H_; dx = (E - W) * 111320 * math.cos(math.radians((S + N) / 2)) / W_
p = np.pad(ndimage.gaussian_filter(dem, 0.7), 1, mode='edge')
a, b, c = p[:-2, :-2], p[:-2, 1:-1], p[:-2, 2:]
d, f = p[1:-1, :-2], p[1:-1, 2:]
g, hh, i_ = p[2:, :-2], p[2:, 1:-1], p[2:, 2:]
slope = np.degrees(np.arctan(np.hypot(((c + 2 * f + i_) - (a + 2 * d + g)) / (8 * dx), ((g + 2 * hh + i_) - (a + 2 * b + c)) / (8 * dy))))
print('relleu', W_, 'x', H_, f'{(dx + dy) / 2:.0f} m', flush=True)

# --- Graella de reg_info (Mercator): cara, roca i arbre, i el pendent i l'altura de cada cel·la ---
info = np.asarray(Image.open('data/reg_info.png').convert('RGB')).astype(np.int16)
sec, rock, tree = info[..., 0] // 28, info[..., 1] // 80, info[..., 2] // 40
gh, gw = sec.shape
my = lambda la: math.log(math.tan(math.pi / 4 + math.radians(la) / 2))
ys = my(N) - (my(N) - my(S)) * (np.arange(gh) + .5) / gh
glat = np.degrees(2 * np.arctan(np.exp(ys)) - math.pi / 2)
glon = W + (E - W) * (np.arange(gw) + .5) / gw
rb = np.clip(((N - np.concatenate([[N], (glat[:-1] + glat[1:]) / 2, [S]])) / (N - S) * H_).astype(int), 0, H_)
cb = np.clip(((np.concatenate([[W], (glon[:-1] + glon[1:]) / 2, [E]]) - W) / (E - W) * W_).astype(int), 0, W_)
r0, r1 = rb[:-1][:, None], np.minimum(np.maximum(rb[1:], rb[:-1] + 1), H_)[:, None]
c0, c1 = cb[:-1][None, :], np.minimum(np.maximum(cb[1:], cb[:-1] + 1), W_)[None, :]
n = (r1 - r0) * (c1 - c0)
def box(A):  # mitjana dels píxels de 25 m que cauen a cada cel·la
    T = np.pad(A.astype(np.float64).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    return ((T[r1, c1] - T[r0, c1] - T[r1, c0] + T[r0, c0]) / n).astype(np.float32)
sl_mean, sl_steep, el = box(slope), box(slope > STEEP), box(dem)
cell_m = 40075016.686 * math.cos(math.radians((S + N) / 2)) * (E - W) / 360 / gw
cell_ha = cell_m ** 2 / 1e4

# --- Zones: trossos seguits; els grans es parteixen en quadres de 2,5 km ---
cand = (tree > 0) & ((rock == 1) | (rock == 3)) & (el >= 200) & (el <= 800)
cand = ndimage.binary_opening(cand, iterations=1)
lab, nl = ndimage.label(cand, structure=np.ones((3, 3)))
area = ndimage.sum(np.ones_like(lab), lab, np.arange(1, nl + 1)) * cell_ha
big = np.isin(lab, np.nonzero(area > BIG_HA)[0] + 1)
k = max(1, round(CELL_KM * 1000 / cell_m))
yy, xx = np.mgrid[0:gh, 0:gw]
cellid = (yy // k) * (gw // k + 1) + (xx // k) + 1
lab2 = np.where(big, 0, lab)
# dins de cada quadre, cada part seguida de la zona gran és una zona nova
nxt = nl + 1
for cid in np.unique(cellid[big]):
    m = big & (cellid == cid)
    l, nn = ndimage.label(m, structure=np.ones((3, 3)))
    lab2[m] = l[m] + nxt - 1
    nxt += nn
TREES = ['', 'pinar', 'alzinar', 'roureda', 'matollar', 'avellaners']
zones = []
for L, sl in enumerate(ndimage.find_objects(lab2), 1):
    if sl is None: continue
    m = lab2[sl] == L
    ncell = int(m.sum())
    if ncell * cell_ha < MIN_HA: continue
    s_, t_, e_, r_ = sec[sl][m], tree[sl][m], el[sl][m], rock[sl][m]
    ys_, xs_ = np.nonzero(m); cy, cx = ys_.mean(), xs_.mean()
    j = np.argmin((ys_ - cy) ** 2 + (xs_ - cx) ** 2)  # punt de la zona més proper al centre, perquè l'agulla caigui dins
    y, x = ys_[j] + sl[0].start, xs_[j] + sl[1].start
    tc = np.bincount(t_, minlength=6)
    zones.append(dict(lat=round(float(glat[y]), 5), lng=round(float(glon[x]), 5), ha=round(ncell * cell_ha),
                      ob=round(float(np.isin(s_, [7, 0, 1]).mean()), 2), so=round(float(np.isin(s_, [3, 4, 5]).mean()), 2),
                      alt=int(np.median(e_)), arbre=TREES[int(tc[1:].argmax()) + 1],
                      bo=round(float((tc[2] + tc[3] + tc[5]) / ncell), 2), acida=round(float((r_ == 1).mean()), 2),
                      pend=int(round(float(sl_mean[sl][m].mean()))), emp=round(float(sl_steep[sl][m].mean()), 2)))
zones.sort(key=lambda z: -z['ha'])
R['zones'] = zones
R['criteris'] = dict(alt=[200, 800], min_ha=MIN_HA, quadre_km=CELL_KM)
json.dump(R, open('data/region.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print('zones', len(zones), 'la més gran', zones[0]['ha'], 'ha', 'pendent', np.percentile([z['pend'] for z in zones], [10, 50, 90]))
