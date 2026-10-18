"""Suavitza la vora de les capes regionals: es fonen en un cercle de ~48-52 km al voltant de Torredembarra,
en lloc d'acabar en un quadrat tallat."""
import json, math, numpy as np
from PIL import Image
R = json.load(open('data/region.json', encoding='utf-8'))
(S, W), (N, E) = R['bounds']; H = R['home']
my = lambda la: math.log(math.tan(math.pi / 4 + math.radians(la) / 2))
for f in ['data/reg_cares.png', 'data/reg_acid.png']:
    im = Image.open(f).convert('RGBA'); w, h = im.size; a = np.asarray(im).copy()
    xs = W + (E - W) * (np.arange(w) + .5) / w
    ys = my(N) - (my(N) - my(S)) * (np.arange(h) + .5) / h
    lats = np.degrees(2 * np.arctan(np.exp(ys)) - math.pi / 2)
    dy = (lats[:, None] - H['lat']) * 111.32; dx = (xs[None, :] - H['lng']) * 111.32 * math.cos(math.radians(H['lat']))
    d = np.hypot(dx, dy)
    fade = np.clip((52 - d) / 5, 0, 1)
    a[..., 3] = (a[..., 3] * fade).astype(np.uint8)
    Image.fromarray(a, 'RGBA').save(f, optimize=True); print(f, 'ok')
