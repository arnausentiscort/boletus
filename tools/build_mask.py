"""Màscares per al color de "Bolets ara": tiles/mask_rov i tiles/mask_ceps (z8-z12).

El color de la pluja només s'ha de veure on hi ha el bosc que toca:
  - rovellons: pinar (Mapa de cobertes del sòl de l'ICGC, 2023);
  - ceps: alzinar o surera, roureda o avellaners, sobre terra àcida.
Cada rajola és blanca amb transparència (opac = hi ha aquell bosc). L'app hi retalla el color.
Les rajoles buides no es desen (l'app les entén com "aquí no hi ha bosc").
S'executa des de site/: python tools/build_mask.py (fa servir la memòria .cat_cache/ de build_cat.py)."""
import glob, json, os, re, shutil
import numpy as np
from PIL import Image
from scipy import ndimage

CACHE = '.cat_cache'; Z = 12
CLS = {int(k.split(':')[1]): v for k, v in json.load(open(f'{CACHE}/classes.json')).items() if k.startswith('cobertes_2023:')}
OUT = {'rov': 'tiles_mask_rov', 'ceps': 'tiles_mask_ceps'}
for d in OUT.values(): shutil.rmtree(d, ignore_errors=True)

def save(base, z, x, y, a):
    if not a.any(): return False
    os.makedirs(f'{base}/{z}/{x}', exist_ok=True)
    img = np.zeros(a.shape + (2,), np.uint8); img[..., 0] = 255; img[..., 1] = a
    Image.fromarray(img, 'LA').save(f'{base}/{z}/{x}/{y}.png', optimize=True); return True

done = {k: set() for k in OUT}
for f in sorted(glob.glob(f'{CACHE}/raw_*.npz')):
    bx, by = map(int, re.findall(r'raw_(\d+)_(\d+)', f)[0])
    cob = np.load(f)['cob']
    key = (cob[..., 0].astype(np.int32) << 16) | (cob[..., 1].astype(np.int32) << 8) | cob[..., 2]
    cols, inv = np.unique(key.ravel(), return_inverse=True)
    cl = np.array([CLS.get(int(c), 0) for c in cols], np.uint8)[inv].reshape(key.shape)
    unk = ~np.isin(key, list(CLS)) & (key != 0xFFFFFF) & (key != 0)
    if unk.any() and (~unk).any():
        _, (iy, ix) = ndimage.distance_transform_edt(unk, return_indices=True); cl[unk] = cl[iy[unk], ix[unk]]
    # roca (1 àcida, 2 calcària, 3 barrejada) del mateix bloc, a mitja resolució
    b = f'{CACHE}/b_{bx}_{by}.npz'
    # (el bloc b_ només cobreix les rajoles útils, sense el marge d'una rajola de cada costat)
    core = cl.shape[0] - 512; rock = np.zeros(cl.shape, np.uint8)
    if os.path.exists(b):
        r = np.load(b)['rock']; rock[256:256 + core, 256:256 + core] = np.kron(r, np.ones((core // r.shape[0], core // r.shape[1]), np.uint8))
    m = {'rov': cl == 1, 'ceps': np.isin(cl, [2, 3, 5]) & np.isin(rock, [1, 3])}
    n = cl.shape[0] // 256 - 2
    for k, mk in m.items():
        mk = ndimage.binary_opening(ndimage.binary_closing(mk, iterations=1), iterations=1)
        a = (mk * 255).astype(np.uint8)
        for j in range(n):
            for i in range(n):
                if save(OUT[k], Z, bx + i, by + j, a[(j + 1) * 256:(j + 2) * 256, (i + 1) * 256:(i + 2) * 256]): done[k].add((bx + i, by + j))
    print(f, flush=True)
for k, base in OUT.items():
    lvl = done[k]
    for z in range(Z - 1, 7, -1):
        up = {(x // 2, y // 2) for x, y in lvl}; keep = set()
        for X, Y in up:
            c = Image.new('LA', (512, 512), (255, 0))
            for dx in (0, 1):
                for dy in (0, 1):
                    p = f'{base}/{z + 1}/{2 * X + dx}/{2 * Y + dy}.png'
                    if os.path.exists(p): c.paste(Image.open(p), (dx * 256, dy * 256))
            if save(base, z, X, Y, np.array(c.resize((256, 256), Image.BOX))[..., 1]): keep.add((X, Y))
        lvl = keep; print(k, 'z', z, len(keep), flush=True)
    shutil.rmtree(f'tiles/mask_{k}', ignore_errors=True); shutil.move(base, f'tiles/mask_{k}')
print('fet')
