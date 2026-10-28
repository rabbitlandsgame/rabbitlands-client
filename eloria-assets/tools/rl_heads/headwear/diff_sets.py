"""Pixel comparison of two render sets with the same file names.

    diff_sets.py <dir_a> <dir_b>  -> per file: max abs channel difference, share of pixels differing
"""
import os
import sys

import numpy as np
from PIL import Image

a, b = sys.argv[1], sys.argv[2]
names = sorted(f for f in os.listdir(a) if f.endswith('.png'))
same = 0
for n in names:
    pb = os.path.join(b, n)
    if not os.path.exists(pb):
        print('%-50s missing in b' % n)
        continue
    x = np.asarray(Image.open(os.path.join(a, n)).convert('RGB'), dtype=np.int16)
    y = np.asarray(Image.open(pb).convert('RGB'), dtype=np.int16)
    d = np.abs(x - y)
    share = float((d.max(-1) > 8).mean())
    if share == 0.0:
        same += 1
    print('%-50s max %3d  differing %.4f' % (n, int(d.max()), share))
print('%d of %d identical within 8/255' % (same, len(names)))
