"""Outfits for a Live2D model, made from a picture of her wearing them.

The picture is cleaned into an outfit texture: the background, her face, and the hair painted over the
clothes are taken out (the clothes behind that hair are filled in), so her own face and moving hair go
on top of it. Her eyes in the picture say where it sits on her model."""
from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage

MAX_SIDE = 1600  # Larger pictures are scaled down; an outfit covers part of a small window.


class OutfitError(ValueError):
    pass


def _pixels(image: QImage) -> np.ndarray:
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = image.width(), image.height()
    data = np.frombuffer(image.constBits(), np.uint8).reshape(height, image.bytesPerLine() // 4, 4)
    return data[:, :width].astype(np.float32)


def _image(pixels: np.ndarray) -> QImage:
    data = np.ascontiguousarray(np.clip(pixels, 0, 255).astype(np.uint8))
    height, width = data.shape[:2]
    return QImage(data.data, width, height, width * 4, QImage.Format.Format_RGBA8888).copy()


def _components(mask):
    """Connected regions of a mask (4-neighbour), as lists of (y, x) arrays, largest first."""
    labels = np.zeros(mask.shape, np.int32)
    regions, current = [], 0
    ys, xs = np.nonzero(mask)
    for y, x in zip(ys, xs):
        if labels[y, x]:
            continue
        current += 1
        stack, points = [(y, x)], []
        labels[y, x] = current
        while stack:
            cy, cx = stack.pop()
            points.append((cy, cx))
            for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                if 0 <= ny < mask.shape[0] and 0 <= nx < mask.shape[1] and mask[ny, nx] and not labels[ny, nx]:
                    labels[ny, nx] = current
                    stack.append((ny, nx))
        regions.append(np.array(points))
    return sorted(regions, key=len, reverse=True)


def find_eyes(pixels):
    """Her two irises (red), centre points [(x, y), (x, y)] left to right, from the picture's upper part."""
    height, width = pixels.shape[:2]
    r, g, b = pixels[..., 0], pixels[..., 1], pixels[..., 2]
    top, bottom = int(height * .15), int(height * .62)
    red = (r > 90) & (r - g > 45) & (r - b > 10) & (b - g > 0)  # Crimson to rose: her eyes, not skin or blush.
    red[:top], red[bottom:] = False, False
    small = max(1, width // 256)
    regions = [region for region in _components(red[::small, ::small]) if len(region) >= 4]
    for i, first in enumerate(regions[:8]):
        for second in regions[i + 1:8]:
            (y1, x1), (y2, x2) = first.mean(0), second.mean(0)
            distance = abs(x1 - x2) * small
            # A pair: side by side, level, a believable distance apart.
            if abs(y1 - y2) * small < distance * .25 and width * .08 < distance < width * .5:
                eyes = sorted([(x1 * small, y1 * small), (x2 * small, y2 * small)])
                return [(float(x), float(y)) for x, y in eyes]
    raise OutfitError("Her eyes could not be found in this picture. Use a picture of her facing forward, "
                      "like her avatar, with her eyes open.")


def _grow(mask, steps=1):
    for _ in range(steps):
        grown = mask.copy()
        grown[1:] |= mask[:-1]
        grown[:-1] |= mask[1:]
        grown[:, 1:] |= mask[:, :-1]
        grown[:, :-1] |= mask[:, 1:]
        mask = grown
    return mask


def _background(pixels, hair):
    """The plain background: the top corners' colour, reached from the edges through it or her hair
    (her long hair walls off pockets of background beside her shoulders)."""
    height, width = pixels.shape[:2]
    rgb = pixels[..., :3]
    corners = np.concatenate([rgb[:8, :8].reshape(-1, 3), rgb[:8, -8:].reshape(-1, 3)])
    colour = np.median(corners, axis=0)
    plain = (np.abs(rgb - colour).sum(-1) < 54) | (pixels[..., 3] < 20)
    passable = plain | hair
    reached = np.zeros((height, width), bool)
    reached[0], reached[:, 0], reached[:, -1] = plain[0], plain[:, 0], plain[:, -1]
    while True:  # Grow from the edges, one pixel a step, until nothing changes.
        grown = _grow(reached) & passable
        if (grown == reached).all():
            return reached & plain
        reached = grown


def _fill(pixels, holes, known, steps=600):
    """Paints the holes in from the known pixels around them, as if the hair over the clothes were lifted."""
    colour = np.where(known[..., None], pixels[..., :3], 0)
    weight = known.astype(np.float32)[..., None]
    todo = holes & ~known

    def spread(values):
        total = np.zeros_like(values)
        total[1:] += values[:-1]
        total[:-1] += values[1:]
        total[:, 1:] += values[:, :-1]
        total[:, :-1] += values[:, 1:]
        return total

    for _ in range(steps):
        count = spread(weight)[..., 0]
        reach = todo & (count > 0)
        if not reach.any():
            break
        colour[reach] = spread(colour * weight)[reach] / count[reach][:, None]
        weight[reach] = 1
        todo &= ~reach
    result = pixels.copy()
    result[..., :3] = np.where(holes[..., None], colour, pixels[..., :3])
    result[..., 3] = np.where(holes, 255, pixels[..., 3])
    return result


def prepare(image: QImage):
    """The outfit texture and her eyes in it. Raises OutfitError when the picture cannot be used."""
    if image.isNull():
        raise OutfitError("That picture could not be opened.")
    if max(image.width(), image.height()) > MAX_SIDE:
        image = image.scaled(MAX_SIDE, MAX_SIDE, aspectMode=1, mode=1)  # Keep aspect, smooth.
    pixels = _pixels(image)
    eyes = find_eyes(pixels)
    height, width = pixels.shape[:2]
    (lx, ly), (rx, ry) = eyes
    spacing = rx - lx
    r, g, b = pixels[..., 0], pixels[..., 1], pixels[..., 2]
    # Her hair is blue, from deep shadow to white-blue shine; her skin a warm near-white. Both come
    # from her own model. A little margin takes the hair's outlines too.
    hair = _grow(((b - r > 24) & (b - g > 8) & (b > 70)) | ((b - r > 10) & (b > 200) & (g > 180)), 4)
    background = _background(pixels, hair)
    # Her face is her model's; her neck is the picture's (a model's neck is often unpainted under a
    # high collar), cut off just under her chin, where her model's face covers the join.
    rows = np.arange(height)[:, None]
    chin = (ly + ry) / 2 + spacing * .8
    head = np.broadcast_to(rows < chin, (height, width))
    outfit = ~background & ~head
    clothes = outfit & ~hair & (pixels[..., 3] > 140)
    clothes &= _density(clothes, 4) > .4  # No stray specks.
    # Hair over the clothes (with clothes on both sides of it along the row) is lifted and the clothes
    # filled in behind it; hair beside her, past her clothes, becomes see-through.
    columns = np.arange(width)[None, :]
    any_row = clothes.any(1)
    left = np.where(any_row, clothes.argmax(1), width)[:, None]
    right = np.where(any_row, width - 1 - clothes[:, ::-1].argmax(1), -1)[:, None]
    under = outfit & hair & (columns > left) & (columns < right)
    pixels = pixels.copy()
    pixels[..., 3] = np.where(clothes, pixels[..., 3], 0)
    return _image(_fill(pixels, under, clothes)), eyes


def _density(mask, radius):
    """How much of each pixel's neighbourhood (a square, 2·radius + 1 wide) is in the mask, 0..1."""
    padded = np.pad(mask.astype(np.float32), radius + 1)
    total = padded.cumsum(0).cumsum(1)
    side = 2 * radius + 1
    area = total[side:, side:] - total[:-side, side:] - total[side:, :-side] + total[:-side, :-side]
    return area[:mask.shape[0], :mask.shape[1]] / side ** 2
