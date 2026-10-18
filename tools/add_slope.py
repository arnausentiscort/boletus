"""Afegeix el pendent a cada zona de data/region.json, amb el relleu MDT25 de l'IGN (25 m, més fi que el Terrarium).

Per a cada zona desa pend (pendent mitjà, en graus) i emp (part del terreny amb més de 25°, on costa caminar i buscar).
Les zones es tornen a trobar amb data/reg_info.png (cara ×28, roca ×80, arbre ×40) i el punt de cada zona.
S'ha d'executar després de build_region.py."""
import io, json, math, subprocess
import concurrent.futures as cf
import numpy as np
from PIL import Image
from scipy import ndimage

R = json.load(open('data/region.json', encoding='utf-8'))
(S, W), (N, E) = R['bounds']
STEEP = 25

def get(url):
    for _ in range(4):
        r = subprocess.run(['curl', '-sfL', '--max-time', '180', url], capture_output=True)
        if not r.returncode: return r.stdout
    raise RuntimeError(url)

# --- Relleu de 25 m en trossos ---
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
H_, W_ = dem.shape
dy = (N - S) * 111320 / H_; dx = (E - W) * 111320 * math.cos(math.radians((S + N) / 2)) / W_
p = np.pad(ndimage.gaussian_filter(dem, 0.7), 1, mode='edge')
a, b, c = p[:-2, :-2], p[:-2, 1:-1], p[:-2, 2:]
d, f = p[1:-1, :-2], p[1:-1, 2:]
g, hh, i_ = p[2:, :-2], p[2:, 1:-1], p[2:, 2:]
slope = np.degrees(np.arctan(np.hypot(((c + 2 * f + i_) - (a + 2 * d + g)) / (8 * dx), ((g + 2 * hh + i_) - (a + 2 * b + c)) / (8 * dy))))
print('relleu', W_, 'x', H_, f'{(dx + dy) / 2:.0f} m', flush=True)

# --- Zones sobre la graella de reg_info (Mercator) ---
info = np.asarray(Image.open('data/reg_info.png').convert('RGB')).astype(np.int16)
sec, rock, tree = info[..., 0] // 28, info[..., 1] // 80, info[..., 2] // 40
gh, gw = sec.shape
my = lambda la: math.log(math.tan(math.pi / 4 + math.radians(la) / 2))
ys = my(N) - (my(N) - my(S)) * (np.arange(gh) + .5) / gh
glat = np.degrees(2 * np.arctan(np.exp(ys)) - math.pi / 2)
glon = W + (E - W) * (np.arange(gw) + .5) / gw
ri = np.clip(((N - glat) / (N - S) * H_).astype(int), 0, H_ - 1)
ci = np.clip(((glon - W) / (E - W) * W_).astype(int), 0, W_ - 1)
# pendent i altura de cada cel·la: mitjana i part empinada dels píxels de 25 m que hi cauen
sl_mean = np.zeros((gh, gw), np.float32); sl_steep = np.zeros((gh, gw), np.float32); el = np.zeros((gh, gw), np.float32)
rb = np.clip(((N - np.concatenate([[N], (glat[:-1] + glat[1:]) / 2, [S]])) / (N - S) * H_).astype(int), 0, H_)
cb = np.clip(((np.concatenate([[W], (glon[:-1] + glon[1:]) / 2, [E]]) - W) / (E - W) * W_).astype(int), 0, W_)
cs = np.pad(slope.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
st = np.pad((slope > STEEP).astype(np.float32).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
r0, r1 = rb[:-1][:, None], np.maximum(rb[1:], rb[:-1] + 1)[:, None]
c0, c1 = cb[:-1][None, :], np.maximum(cb[1:], cb[:-1] + 1)[None, :]
r1 = np.minimum(r1, H_); c1 = np.minimum(c1, W_)
n = (r1 - r0) * (c1 - c0)
box = lambda T: (T[r1, c1] - T[r0, c1] - T[r1, c0] + T[r0, c0]) / n
sl_mean, sl_steep = box(cs), box(st)
el = dem[ri[:, None], ci[None, :]]

cand = (tree > 0) & ((rock == 1) | (rock == 3)) & (el >= 200) & (el <= 800)
lab, nl = ndimage.label(cand, structure=np.ones((3, 3)))
idx = np.arange(1, nl + 1)
mean_l = ndimage.mean(sl_mean, lab, idx); steep_l = ndimage.mean(sl_steep, lab, idx)
dist, (iy, ix) = ndimage.distance_transform_edt(lab == 0, return_indices=True)
miss = 0
for z in R['zones']:
    y = int((my(N) - my(z['lat'])) / (my(N) - my(S)) * gh); x = int((z['lng'] - W) / (E - W) * gw)
    y, x = min(max(y, 0), gh - 1), min(max(x, 0), gw - 1)
    if dist[y, x] > 3: miss += 1; continue
    L = lab[iy[y, x], ix[y, x]]
    z['pend'] = int(round(float(mean_l[L - 1]))); z['emp'] = round(float(steep_l[L - 1]), 2)
json.dump(R, open('data/region.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
v = [z['pend'] for z in R['zones'] if 'pend' in z]
print('zones', len(R['zones']), 'sense pendent', miss, 'pendent mitjà', np.percentile(v, [10, 50, 90]))
