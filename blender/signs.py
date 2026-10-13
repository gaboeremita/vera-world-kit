"""Pixel-font sign textures: 5x7 glyphs, one texel per font pixel, sampled with nearest filtering."""
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
}


def text_pixels(text, scale=1):
    """Boolean array (rows, cols) for the text, top row first."""
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


def sign_image(key, text, ink, paper, border=None, aspect=None):
    """Image with the text centred; aspect (width / height in metres) sizes the canvas so letters keep square pixels."""
    name = f"sign {key}"
    import region as config
    folder = config.TEXTURES
    path = os.path.join(folder, f"sign-{key}.png")
    pixels = text_pixels(text)
    rows, cols = pixels.shape
    height = rows + 4
    width = cols + 6
    if aspect:
        width = max(width, int(round(height * aspect)))
    canvas = np.zeros((height, width, 4), dtype=np.float32)
    canvas[:, :, :3] = paper
    canvas[:, :, 3] = 1.0
    if border is not None:
        canvas[0, :, :3] = border
        canvas[-1, :, :3] = border
        canvas[:, 0, :3] = border
        canvas[:, -1, :3] = border
    top = (height - rows) // 2
    left = (width - cols) // 2
    region = canvas[top:top + rows, left:left + cols, :3]
    region[pixels] = ink
    image = bpy.data.images.get(name)
    if image is not None:
        bpy.data.images.remove(image)
    image = bpy.data.images.new(name, width, height, alpha=False)
    image.pixels.foreach_set(np.flipud(canvas).ravel())
    os.makedirs(folder, exist_ok=True)
    image.filepath_raw = path
    image.file_format = "PNG"
    image.save()
    return image


def sign_material(key, image):
    name = f"Sign text {key}"
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    import lib
    bsdf = lib.principled(mat)
    tex = next((n for n in nodes if n.type == "TEX_IMAGE"), None) or nodes.new("ShaderNodeTexImage")
    tex.image = image
    tex.interpolation = "Closest"
    mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    return mat
