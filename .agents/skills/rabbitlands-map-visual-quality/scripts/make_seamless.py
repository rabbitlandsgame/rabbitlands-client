"""make_seamless.py <in.png> <out.png> [--size N] [--band F]

Makes a square texture wrap seamlessly. The image is rolled by half a tile so
its old edges meet in the middle, and the middle band is replaced by the
unrolled original along a minimum-error cut (image quilting, Efros & Freeman):
the cut follows the path where the two images already agree, so structured
textures (flagstones, pebbles) keep whole stones instead of ghosting. The cut
is feathered by a few pixels. Then the tile's own edges are the original's
interior, which is continuous, and the seam the generator left is gone.
"""
import argparse

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter


def min_cut(cost):
    """Vertical minimum-cost path through cost (h x w): returns column per row."""
    h, w = cost.shape
    acc = cost.copy()
    back = np.zeros((h, w), dtype=np.int64)
    for y in range(1, h):
        prev = acc[y - 1]
        left = np.r_[np.inf, prev[:-1]]
        right = np.r_[prev[1:], np.inf]
        stack = np.vstack([left, prev, right])
        idx = np.argmin(stack, axis=0)
        acc[y] += stack[idx, np.arange(w)]
        back[y] = idx - 1
    path = np.zeros(h, dtype=np.int64)
    path[-1] = int(np.argmin(acc[-1]))
    for y in range(h - 1, 0, -1):
        path[y - 1] = np.clip(path[y] + back[y, path[y]], 0, w - 1)
    return path


def seam_mask(a, b, band, axis):
    """Mask (1 = take b) over the full image: b inside a band around the centre, cut along min error."""
    if axis == 1:
        a, b = a.transpose(1, 0, 2), b.transpose(1, 0, 2)
    h, w, _ = a.shape
    lo, hi = w // 2 - band // 2, w // 2 + band // 2
    err = ((a[:, lo:hi] - b[:, lo:hi]) ** 2).sum(axis=2)
    err = gaussian_filter(err, 1.0)
    # Two cuts: one in the left half of the band, one in the right half.
    left = min_cut(err[:, : band // 2]) + lo
    right = min_cut(err[:, band // 2:]) + lo + band // 2
    mask = np.zeros((h, w), dtype=np.float32)
    cols = np.arange(w)[None, :]
    mask[(cols >= left[:, None]) & (cols < right[:, None])] = 1.0
    if axis == 1:
        mask = mask.T
    return mask


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('src')
    parser.add_argument('dst')
    parser.add_argument('--size', type=int, default=1024)
    parser.add_argument('--band', type=float, default=0.34, help='share of the tile the middle band spans')
    parser.add_argument('--feather', type=float, default=3.0)
    parser.add_argument('--flatten', type=float, default=0.12,
                        help='blur radius (share of the tile) of the light falloff divided out; 0 keeps it')
    args = parser.parse_args()
    img = Image.open(args.src).convert('RGB')
    side = min(img.size)
    img = img.crop(((img.width - side) // 2, (img.height - side) // 2,
                    (img.width - side) // 2 + side, (img.height - side) // 2 + side))
    img = img.resize((args.size, args.size), Image.LANCZOS)
    a = np.asarray(img, dtype=np.float32) / 255.0
    n = args.size
    if args.flatten > 0:
        # Low-frequency light falloff (generators darken tile edges) repeats as a
        # grid: divide it out, keeping the mean brightness and every detail.
        lum = a.mean(axis=2)
        low = gaussian_filter(lum, n * args.flatten, mode='wrap')
        a = np.clip(a * (lum.mean() / np.maximum(low, 1e-3))[..., None], 0, 1)
    band = int(n * args.band) // 2 * 2
    # Rolled copy: its outer edges wrap (they were neighbours in the middle of a).
    rolled = np.roll(a, (n // 2, n // 2), axis=(0, 1))
    mx = seam_mask(rolled, a, band, axis=0)  # vertical seam band in the middle columns
    my = seam_mask(rolled, a, band, axis=1)  # horizontal seam band in the middle rows
    mask = np.maximum(mx, my)
    mask = gaussian_filter(mask, args.feather)
    out = rolled * (1 - mask[..., None]) + a * mask[..., None]
    Image.fromarray(np.clip(out * 255 + 0.5, 0, 255).astype(np.uint8)).save(args.dst)
    # Report how well the tile wraps: edge-to-edge difference vs typical neighbour difference.
    wrap_x = np.abs(out[:, 0] - out[:, -1]).mean()
    wrap_y = np.abs(out[0] - out[-1]).mean()
    inner = np.abs(out[:, 1:] - out[:, :-1]).mean()
    print(f'{args.dst}: wrap x {wrap_x:.4f} y {wrap_y:.4f} vs neighbour {inner:.4f}')


if __name__ == '__main__':
    main()
