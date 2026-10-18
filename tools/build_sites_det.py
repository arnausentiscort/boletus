"""Detall de 5 m al voltant de cada lloc de data/llocs.json, amb el relleu MDT05 de l'IGN.

Per a cada lloc desa data/det/<id>.png (R = cara ×28, G = pendent en graus, B = altura − altura mínima)
i data/det/<id>.json (límits, altura mínima). L'app ho fa servir per pintar les cares i fer l'anàlisi."""
import io, json, math, os, subprocess
import numpy as np
from PIL import Image
from scipy import ndimage

os.makedirs('data/det', exist_ok=True)
llocs = json.load(open('data/llocs.json', encoding='utf-8'))['sites']
DL, DN = 0.0080, 0.0105  # ~890 m al nord/sud i ~880 m a l'est/oest

def get(url):
    r = subprocess.run(['curl', '-sfL', '--max-time', '120', url], capture_output=True)
    if r.returncode: raise RuntimeError(url)
    return r.stdout

for s in llocs:
    S, N, W, E = s['lat'] - DL, s['lat'] + DL, s['lng'] - DN, s['lng'] + DN
    u = ('https://servicios.idee.es/wcs-inspire/mdt?SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverage'
         f'&COVERAGEID=Elevacion4258_5&SUBSET=Lat({S},{N})&SUBSET=Long({W},{E})&FORMAT=image/tiff')
    z = np.asarray(Image.open(io.BytesIO(get(u))), np.float32)
    h, w = z.shape
    dy = (N - S) * 111320 / h
    dx = (E - W) * 111320 * math.cos(math.radians(s['lat'])) / w
    zs = ndimage.gaussian_filter(z, 1.6)  # el model ve en metres sencers: el suavitzat treu esglaons
    p = np.pad(zs, 1, mode='edge')
    a, b, c = p[:-2, :-2], p[:-2, 1:-1], p[:-2, 2:]
    d, f = p[1:-1, :-2], p[1:-1, 2:]
    g, hh, i = p[2:, :-2], p[2:, 1:-1], p[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * dx)
    dzdy = ((g + 2 * hh + i) - (a + 2 * b + c)) / (8 * dy)   # fila avall = sud
    slope = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
    sec = (np.round(((np.degrees(np.arctan2(-dzdx, dzdy)) + 360) % 360) / 45).astype(np.int16) % 8)
    sec[slope < 2.5] = 8
    emin = int(z.min())
    rgb = np.stack([sec * 28, np.clip(np.round(slope), 0, 90), np.clip(z - emin, 0, 255)], -1).astype(np.uint8)
    Image.fromarray(rgb, 'RGB').save(f"data/det/{s['id']}.png", optimize=True)
    json.dump(dict(bounds=[[S, W], [N, E]], emin=emin, size=[w, h], m=round((dx + dy) / 2, 1)),
              open(f"data/det/{s['id']}.json", 'w'))
    print(s['name'], w, 'x', h, f"{(dx + dy) / 2:.1f} m/píxel", 'alt', emin, int(z.max()))
