"""Pixel-font sign textures: 5x7 glyphs, one texel per font pixel, sampled with nearest filtering."""
import math
import os

import bpy
import numpy as np


GLYPHS = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["01110", "00100", "00100", "00100", "00100", "00100", "01110"],
    "J": ["00111", "00010", "00010", "00010", "00010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "10001", "11001", "10101", "10011", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11111", "00010", "00100", "00010", "00001", "10001", "01110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
    "/": ["00001", "00001", "00010", "00100", "01000", "10000", "10000"],
    ".": ["00000", "00000", "00000", "00000", "00000", "01100", "01100"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    "&": ["01100", "10010", "10100", "01000", "10101", "10010", "01101"],
    "'": ["00100", "00100", "01000", "00000", "00000", "00000", "00000"],
    ":": ["00000", "01100", "01100", "00000", "01100", "01100", "00000"],
    "~": ["00000", "00000", "01000", "10101", "00010", "00000", "00000"],
    "_": ["00000", "00000", "00000", "00000", "00000", "00000", "11111"],
    " ": ["00000"] * 7,
    "!": ["00100", "00100", "00100", "00100", "00100", "00000", "00100"],
    ",": ["00000", "00000", "00000", "00000", "01100", "00100", "01000"],
    "$": ["00100", "01111", "10100", "01110", "00101", "11110", "00100"],
    "(": ["00010", "00100", "01000", "01000", "01000", "00100", "00010"],
    ")": ["01000", "00100", "00010", "00010", "00010", "00100", "01000"],
    "+": ["00000", "00100", "00100", "11111", "00100", "00100", "00000"],
    "¡": ["00100", "00000", "00100", "00100", "00100", "00100", "00100"],
    "Á": ["00010", "00100", "01110", "10001", "11111", "10001", "10001"],
    "É": ["00010", "00100", "11111", "10000", "11110", "10000", "11111"],
    "Í": ["00010", "00100", "01110", "00100", "00100", "00100", "01110"],
    "Ó": ["00010", "00100", "01110", "10001", "10001", "10001", "01110"],
    "Ú": ["00010", "00100", "10001", "10001", "10001", "10001", "01110"],
    "Ñ": ["01110", "00000", "10001", "11001", "10101", "10011", "10001"],
    "a": ["00000", "00000", "01110", "00001", "01111", "10001", "01111"],
    "b": ["10000", "10000", "10110", "11001", "10001", "10001", "11110"],
    "c": ["00000", "00000", "01110", "10000", "10000", "10001", "01110"],
    "d": ["00001", "00001", "01101", "10011", "10001", "10001", "01111"],
    "e": ["00000", "00000", "01110", "10001", "11111", "10000", "01110"],
    "f": ["00110", "01001", "01000", "11100", "01000", "01000", "01000"],
    "g": ["00000", "01111", "10001", "10001", "01111", "00001", "01110"],
    "h": ["10000", "10000", "10110", "11001", "10001", "10001", "10001"],
    "i": ["00100", "00000", "01100", "00100", "00100", "00100", "01110"],
    "j": ["00010", "00000", "00110", "00010", "00010", "10010", "01100"],
    "k": ["10000", "10000", "10010", "10100", "11000", "10100", "10010"],
    "l": ["01100", "00100", "00100", "00100", "00100", "00100", "01110"],
    "m": ["00000", "00000", "11010", "10101", "10101", "10001", "10001"],
    "n": ["00000", "00000", "10110", "11001", "10001", "10001", "10001"],
    "o": ["00000", "00000", "01110", "10001", "10001", "10001", "01110"],
    "p": ["00000", "11110", "10001", "10001", "11110", "10000", "10000"],
    "q": ["00000", "01101", "10011", "10001", "01111", "00001", "00001"],
    "r": ["00000", "00000", "10110", "11001", "10000", "10000", "10000"],
    "s": ["00000", "00000", "01111", "10000", "01110", "00001", "11110"],
    "t": ["01000", "01000", "11100", "01000", "01000", "01001", "00110"],
    "u": ["00000", "00000", "10001", "10001", "10001", "10011", "01101"],
    "v": ["00000", "00000", "10001", "10001", "10001", "01010", "00100"],
    "w": ["00000", "00000", "10001", "10001", "10101", "10101", "01010"],
    "x": ["00000", "00000", "10001", "01010", "00100", "01010", "10001"],
    "y": ["00000", "10001", "10001", "10001", "01111", "00001", "01110"],
    "z": ["00000", "00000", "11111", "00010", "00100", "01000", "11111"],
    "á": ["00010", "00100", "01110", "00001", "01111", "10001", "01111"],
    "é": ["00010", "00100", "01110", "10001", "11111", "10000", "01110"],
    "í": ["00010", "00100", "01100", "00100", "00100", "00100", "01110"],
    "ó": ["00010", "00100", "01110", "10001", "10001", "10001", "01110"],
    "ú": ["00010", "00100", "10001", "10001", "10001", "10011", "01101"],
    "ñ": ["01110", "00000", "10110", "11001", "10001", "10001", "10001"],
}


def text_pixels(text, scale=1, keep_case=False):
    """Boolean array (rows, cols) for the text, top row first; capitals only unless keep_case."""
    if not keep_case:
        text = text.upper()
    cols = len(text) * 6 - 1
    grid = np.zeros((7, max(cols, 1)), dtype=bool)
    for index, char in enumerate(text):
        glyph = GLYPHS.get(char, GLYPHS[" "])
        for row, bits in enumerate(glyph):
            for col, bit in enumerate(bits):
                if bit == "1":
                    grid[row, index * 6 + col] = True
    if scale > 1:
        grid = np.kron(grid, np.ones((scale, scale), dtype=bool))
    return grid


def text_width(text, scale=1):
    return max(len(text) * 6 - 1, 1) * scale


class Canvas:
    """Pixel image painted in texels, origin at the top left, saved as a printed texture."""

    def __init__(self, width, height, background):
        self.width, self.height = width, height
        self.pixels = np.zeros((height, width, 3), dtype=np.float32)
        self.pixels[:, :] = background

    def rect(self, x0, y0, x1, y1, colour):
        self.pixels[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = colour

    def frame(self, colour, thickness=1):
        t = thickness
        self.rect(0, 0, self.width, t, colour)
        self.rect(0, self.height - t, self.width, self.height, colour)
        self.rect(0, 0, t, self.height, colour)
        self.rect(self.width - t, 0, self.width, self.height, colour)

    def _disc_mask(self, cx, cy, radius):
        ys, xs = np.mgrid[0:self.height, 0:self.width]
        return (xs + 0.5 - cx) ** 2 + (ys + 0.5 - cy) ** 2 <= radius ** 2

    def circle(self, cx, cy, radius, colour):
        self.pixels[self._disc_mask(cx, cy, radius)] = colour

    def ring(self, cx, cy, outer, inner, colour):
        self.pixels[self._disc_mask(cx, cy, outer) & ~self._disc_mask(cx, cy, inner)] = colour

    def text(self, text, x, y, colour, scale=1, keep_case=True):
        """Draws the text with its top left at (x, y); x="center" centres it. Returns the x after the text."""
        pixels = text_pixels(text, scale, keep_case)
        rows, cols = pixels.shape
        if x == "center":
            x = (self.width - cols) // 2
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.width, x + cols), min(self.height, y + rows)
        if x1 > x0 and y1 > y0:
            target = self.pixels[y0:y1, x0:x1]
            target[pixels[y0 - y:y1 - y, x0 - x:x1 - x]] = colour
        return x + cols

    def sprite(self, rows, palette, x, y, scale=1):
        """Pixel art from rows of characters; palette maps each character to a colour, and unmapped ones stay clear."""
        for r, line in enumerate(rows):
            for c, char in enumerate(line):
                if char in palette:
                    self.rect(x + c * scale, y + r * scale, x + (c + 1) * scale, y + (r + 1) * scale, palette[char])

    def scatter(self, count, colours, seed=0, size=(2, 1)):
        """Small marks in random places and orientations, like sprinkles or terrazzo chips."""
        rng = np.random.default_rng(seed)
        for _ in range(count):
            w, h = size if rng.random() < 0.5 else size[::-1]
            x, y = int(rng.integers(0, self.width)), int(rng.integers(0, self.height))
            self.rect(x, y, min(self.width, x + w), min(self.height, y + h), colours[int(rng.integers(len(colours)))])

    def gradient(self, start, end, vertical=True, x0=0, y0=0, x1=None, y1=None):
        """Blends from start to end, top to bottom (or left to right when not vertical), over the rect or the whole canvas."""
        x1 = self.width if x1 is None else x1
        y1 = self.height if y1 is None else y1
        span = (y1 - y0) if vertical else (x1 - x0)
        t = np.linspace(0.0, 1.0, max(span, 1))[:, None]
        band = (1 - t) * np.array(start) + t * np.array(end)
        if vertical:
            self.pixels[y0:y1, x0:x1] = band[:, None, :]
        else:
            self.pixels[y0:y1, x0:x1] = band[None, :, :]

    def arc_text(self, text, cx, cy, radius, colour, scale=1, advance=6, bottom=False, keep_case=True):
        """Text along a circle centred on (cx, cy): over the top reading clockwise, or along the bottom reading
        left to right, letters standing upright on the circle either way; radius runs to the middle of the letters."""
        chars = text if keep_case else text.upper()
        step = advance * scale / radius
        first = -(len(chars) - 1) / 2 * step
        for index, char in enumerate(chars):
            glyph = GLYPHS.get(char, GLYPHS[" "])
            phi = first + index * step
            if bottom:
                phi = math.pi - phi
                tangent = np.array((-math.cos(phi), -math.sin(phi)))
                down = np.array((math.sin(phi), -math.cos(phi)))
            else:
                tangent = np.array((math.cos(phi), math.sin(phi)))
                down = -np.array((math.sin(phi), -math.cos(phi)))
            centre = np.array((cx, cy)) + radius * np.array((math.sin(phi), -math.cos(phi)))
            for row, bits in enumerate(glyph):
                for col, bit in enumerate(bits):
                    if bit != "1":
                        continue
                    for sx in np.linspace(0, scale, 2 * scale, endpoint=False):
                        for sy in np.linspace(0, scale, 2 * scale, endpoint=False):
                            dx, dy = (col - 2.5) * scale + sx + 0.25, (row - 3.5) * scale + sy + 0.25
                            x, y = centre + dx * tangent + dy * down
                            xi, yi = int(math.floor(x)), int(math.floor(y))
                            if 0 <= xi < self.width and 0 <= yi < self.height:
                                self.pixels[yi, xi] = colour

    def stripes(self, colours, width, vertical=True):
        span = self.width if vertical else self.height
        for start in range(0, span, width):
            colour = colours[(start // width) % len(colours)]
            if vertical:
                self.rect(start, 0, start + width, self.height, colour)
            else:
                self.rect(0, start, self.width, start + width, colour)

    def save(self, key, prefix="print"):
        import region as config
        name = f"{prefix} {key}"
        rgba = np.ones((self.height, self.width, 4), dtype=np.float32)
        rgba[:, :, :3] = self.pixels
        image = bpy.data.images.get(name)
        if image is not None:
            bpy.data.images.remove(image)
        image = bpy.data.images.new(name, self.width, self.height, alpha=False)
        image.pixels.foreach_set(np.flipud(rgba).ravel())
        os.makedirs(config.TEXTURES, exist_ok=True)
        image.filepath_raw = os.path.join(config.TEXTURES, f"{prefix}-{key}.png")
        image.file_format = "PNG"
        image.save()
        return image


def sign_image(key, text, ink, paper, border=None, aspect=None, keep_case=False):
    """Image with the text centred; aspect (width / height in metres) sizes the canvas so letters keep square pixels."""
    rows, cols = text_pixels(text, keep_case=keep_case).shape
    height = rows + 4
    width = cols + 6
    if aspect:
        width = max(width, int(round(height * aspect)))
    canvas = Canvas(width, height, paper)
    if border is not None:
        canvas.frame(border)
    canvas.text(text, "center", (height - rows) // 2, ink, keep_case=keep_case)
    return canvas.save(key, prefix="sign")


def printed_material(name, image):
    """Material that shows the image as painted: the look keeps its UVs and colours and the export packs it into the atlas."""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    import lib
    bsdf = lib.principled(mat)
    tex = next((n for n in nodes if n.type == "TEX_IMAGE"), None) or nodes.new("ShaderNodeTexImage")
    tex.image = image
    tex.interpolation = "Closest"
    mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    mat["printed"] = True
    return mat


def sign_material(key, image):
    return printed_material(f"Sign text {key}", image)
