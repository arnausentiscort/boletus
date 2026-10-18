"""Capa 'Terra àcida' a partir de data/reg_info.png (G = roca: 1 àcida, 2 calcària, 3 barrejada).
La calcària queda coberta amb un vel clar i la terra àcida queda neta, amb una vora lila."""
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage
g = np.asarray(Image.open('data/reg_info.png').convert('RGB'))[..., 1]
acid = ndimage.binary_opening((g == 1) | (g == 3), iterations=1)
calc = ndimage.binary_opening(g == 2, iterations=1) & ~acid
up = lambda m: np.asarray(Image.fromarray((m * 255).astype(np.uint8)).resize((m.shape[1] * 2, m.shape[0] * 2), Image.BILINEAR).filter(ImageFilter.GaussianBlur(1))) > 127
A, C = up(acid), up(calc)
edge = A & ~ndimage.binary_erosion(A, iterations=3)
rgba = np.zeros(A.shape + (4,), np.uint8)
rgba[C] = [238, 234, 226, 165]
rgba[edge] = [110, 45, 150, 240]
Image.fromarray(rgba, 'RGBA').save('data/reg_acid.png', optimize=True)
print('ok', A.mean().round(3), C.mean().round(3))
