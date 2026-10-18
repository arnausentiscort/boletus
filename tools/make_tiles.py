"""Parteix les capes grans (reg_cares.png, reg_acid.png) en rajoles de 256 px (z9-z12), com un mapa normal.
Així el mòbil només carrega el tros que mira i el zoom va fi. Les rajoles buides no es desen."""
import json, math, os, shutil
import numpy as np
from PIL import Image

R = json.load(open('data/region.json', encoding='utf-8'))
(S, W), (N, E) = R['bounds']
Z = 12
X0 = round((W + 180) / 360 * 2**Z)
Y0 = round((1 - math.asinh(math.tan(math.radians(N))) / math.pi) / 2 * 2**Z)
for name in ['cares', 'acid']:
    out = f'tiles/{name}'
    shutil.rmtree(out, ignore_errors=True)
    img = Image.open(f'data/reg_{name}.png').convert('RGBA')
    n = 0
    for z in range(Z, 8, -1):
        f = 2 ** (Z - z)
        x0, y0 = X0 // f, Y0 // f
        # encaixa la imatge a la graella de rajoles d'aquest zoom
        ox, oy = (X0 - x0 * f) * 256, (Y0 - y0 * f) * 256
        big = Image.new('RGBA', (img.width + ox + 256 * f, img.height + oy + 256 * f))
        big.paste(img, (ox, oy))
        small = big.resize((big.width // f, big.height // f), Image.LANCZOS) if f > 1 else big
        for ty in range(small.height // 256):
            for tx in range(small.width // 256):
                t = small.crop((tx * 256, ty * 256, (tx + 1) * 256, (ty + 1) * 256))
                if not np.asarray(t)[..., 3].any():
                    continue
                d = f'{out}/{z}/{x0 + tx}'
                os.makedirs(d, exist_ok=True)
                t.save(f'{d}/{y0 + ty}.png', optimize=True)
                n += 1
    print(name, n, 'rajoles')
