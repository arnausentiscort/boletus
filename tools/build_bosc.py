"""Capa "És bosc?": tiles/bosc/{z}/{x}/{y}.png (z8-z12) per a tot Catalunya.

Surt del Mapa de cobertes del sòl de l'ICGC (2023), el mateix que fa servir build_cat.py (i la seva memòria .cat_cache/).
  - bosc (pinar, alzinar o surera, roureda o altres caducifolis): un vel verd suau, es veu la foto aèria;
  - matollar: vel suau;
  - tot el que no és bosc (conreus, prats, pobles, roca, aigua): vel fosc;
  - la vora del bosc: línia verda.
Així d'un cop d'ull es veu si el que mires és bosc. Tocant el mapa, l'app ho torna a preguntar a l'ICGC (1 m) per contrastar-ho.
S'executa des de site/: python tools/build_bosc.py (uns minuts; no baixa res)."""
import glob, json, os, re, shutil
import numpy as np
from PIL import Image
from scipy import ndimage

CACHE = '.cat_cache'; OUT = 'tiles_bosc'; Z = 12
CLS = {int(k.split(':')[1]): v for k, v in json.load(open(f'{CACHE}/classes.json')).items() if k.startswith('cobertes_2023:')}
VEL, VEL_MAT, VORA, BOSC = (18, 20, 16, 165), (18, 20, 16, 80), (40, 200, 90, 235), (40, 170, 80, 70)

def tile_dir(z, x): d = f'{OUT}/{z}/{x}'; os.makedirs(d, exist_ok=True); return d
shutil.rmtree(OUT, ignore_errors=True)
done = set()
for f in sorted(glob.glob(f'{CACHE}/raw_*.npz')):
    bx, by = map(int, re.findall(r'raw_(\d+)_(\d+)', f)[0])
    cob = np.load(f)['cob']
    key = (cob[..., 0].astype(np.int32) << 16) | (cob[..., 1].astype(np.int32) << 8) | cob[..., 2]
    cols, inv = np.unique(key.ravel(), return_inverse=True)
    cl = np.array([CLS.get(int(c), 0) for c in cols], np.uint8)[inv].reshape(key.shape)
    # els colors sense classe (vores antialiasades, textos) prenen la classe del veí més proper
    unk = ~np.isin(key, list(CLS)) & (key != 0xFFFFFF) & (key != 0)
    if unk.any() and (~unk).any():
        _, (iy, ix) = ndimage.distance_transform_edt(unk, return_indices=True); cl[unk] = cl[iy[unk], ix[unk]]
    bosc = np.isin(cl, [1, 2, 3])
    bosc = ndimage.binary_opening(ndimage.binary_closing(bosc, iterations=1), iterations=1)   # treu soroll d'un píxel
    mat = (cl == 4) & ~bosc
    vora = bosc & ~ndimage.binary_erosion(bosc, iterations=1)
    img = np.zeros(cl.shape + (4,), np.uint8); img[:] = VEL; img[mat] = VEL_MAT; img[bosc] = BOSC; img[vora] = VORA
    img[key == 0] = 0      # fora del mapa de l'ICGC (França, Aragó): sense vel
    n = cl.shape[0] // 256 - 2   # rajoles útils (sense el marge)
    for j in range(n):
        for i in range(n):
            x, y = bx + i, by + j
            t = img[(j + 1) * 256:(j + 2) * 256, (i + 1) * 256:(i + 2) * 256]
            Image.fromarray(t, 'RGBA').save(f'{tile_dir(Z, x)}/{y}.png', optimize=True); done.add((x, y))
    print(f, flush=True)
# nivells més allunyats: cada rajola surt de les quatre de sota
lvl = done
for z in range(Z - 1, 7, -1):
    up = {(x // 2, y // 2) for x, y in lvl}
    for X, Y in up:
        c = Image.new('RGBA', (512, 512))
        for dx in (0, 1):
            for dy in (0, 1):
                p = f'{OUT}/{z + 1}/{2 * X + dx}/{2 * Y + dy}.png'
                if os.path.exists(p): c.paste(Image.open(p), (dx * 256, dy * 256))
        c.resize((256, 256), Image.LANCZOS).save(f'{tile_dir(z, X)}/{Y}.png', optimize=True)
    lvl = up; print('z', z, len(up), flush=True)
shutil.rmtree('tiles/bosc', ignore_errors=True); shutil.move(OUT, 'tiles/bosc'); print('fet')
