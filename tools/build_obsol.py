"""Refà data/obsol.png (obaga en blau, solana en taronja) amb vores suaus.
Pinta on hi ha vegetació on poden sortir bolets: bosc, matollar i avellaners (meta.json -> forest_ids)."""
import json, math, re, numpy as np
from PIL import Image, ImageFilter
D = 'data'
meta = json.load(open(f'{D}/meta.json', encoding='utf-8'))
names = meta['cover_names']
veg = sorted(set(meta['forest_ids']) | {i for i, n in enumerate(names) if re.search(r'Matollar|Altres conreus llenyosos', n)})
meta['forest_ids'] = veg
json.dump(meta, open(f'{D}/meta.json', 'w', encoding='utf-8'), ensure_ascii=False)
gw, gh = meta['grid']; n = gw * gh
raw = open(f'{D}/grid.bin', 'rb').read()
off = n * 2 + n + n * 2
sec = np.frombuffer(raw[off:off + n], np.uint8).reshape(gh, gw); off += n
cov = np.frombuffer(raw[off:off + n], np.uint8).reshape(gh, gw)
v = np.isin(cov, veg)
def mask(ids): return Image.fromarray(((v & np.isin(sec, ids)) * 255).astype(np.uint8), 'L')
size = (gw * 4, gh * 4)
a = np.asarray(mask([7, 0, 1]).resize(size, Image.BICUBIC).filter(ImageFilter.GaussianBlur(3)))
b = np.asarray(mask([3, 4, 5]).resize(size, Image.BICUBIC).filter(ImageFilter.GaussianBlur(3)))
rgba = np.zeros(a.shape + (4,), np.uint8)
rgba[(a > 127) & (a >= b)] = [52, 104, 200, 150]
rgba[(b > 127) & (b > a)] = [232, 132, 48, 135]
Image.fromarray(rgba, 'RGBA').save(f'{D}/obsol.png', optimize=True)
print('classes pintades:', [re.sub(r'^[\d.]+\s*\(\d+\)\s*', '', names[i]) for i in veg])
