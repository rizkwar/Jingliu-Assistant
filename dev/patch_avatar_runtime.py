"""Reproduce local HD and stable-frame changes to mesh-avatar 0.2.1.

Only the pristine pinned bundle, its previously published HD-only build, or the
current patched build are accepted. The runtime's upstream advance() is retained.
"""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PINNED_SHA256 = '691301e4a2a89779617de4f4bf6c407c3003dc27161f5e4a3665566dfcff8e87'
HD_SHA256 = '188ffa03914eb5ed765d98b7aa3cd273bdc5760cc0755ed92dab2ec42e096326'
CURRENT_SHA256 = '1576e6550bcc64860cd4d06921f9a9df067e553bb4bd6301e6a32ffc45086b7e'


def replace_once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Pinned runtime patch did not match; review upstream changes.')
    return text.replace(before, after)


def patch(source):
    # Git's Windows checkout may use CRLF. Hash and emit the canonical LF build.
    source = source.replace(b'\r\n', b'\n')
    digest = hashlib.sha256(source).hexdigest()
    if digest == CURRENT_SHA256:
        return source
    if digest not in (PINNED_SHA256, HD_SHA256):
        raise ValueError('Expected a known pinned runtime; review upstream changes before patching.')
    text = source.decode('utf-8')
    if digest == PINNED_SHA256:
        text = patch_hd(text)
    for before, after in (
        ('function E(M) {', 'function E(M, draw = true, visualDt = M) {'),
        ('const R = A(M), W = H.step(R, M), Q = U.pos, ne = U.rest;',
         'const R = A(M), W = H.step(R, M), Q = U.pos, ne = U.rest;\n    if (!draw) return;'),
        ('$?.update(R, W, M, Fn(', '$?.update(R, W, visualDt, Fn('),
        ('    /** Update motion and lip sync without drawing a hidden preview. */\n    advanceParameters(M) {',
         '    /** Bounded spring steps with a single mesh draw per elapsed frame. */\n    advanceStable(M) {\n      if (!z) advanceFrame(M, (dt, draw, total) => E(dt, draw, total));\n    },\n    /** Update motion and lip sync without drawing a hidden preview. */\n    advanceParameters(M) {'),
    ):
        text = replace_once(text, before, after)
    return ("import {advanceFrame} from './stable-step.js';\n" + text).encode('utf-8')


def patch_hd(text):
    before = 'const x = this.canvas, o = Math.min(window.devicePixelRatio || 1, 2), h = Math.round(x.clientWidth * o), T = Math.round(x.clientHeight * o);'
    after = '''const x = this.canvas, hd = x.dataset.renderQuality === "hd", [h, T] = drawingSize(x.clientWidth, x.clientHeight, window.devicePixelRatio, hd);
      if (this.hd !== hd) {
        this.gl.activeTexture(this.gl.TEXTURE0);
        for (const layer of this.layers) {
          this.gl.bindTexture(this.gl.TEXTURE_2D, layer.tex);
          this.gl.texParameteri(this.gl.TEXTURE_2D, this.gl.TEXTURE_MIN_FILTER, hd ? this.gl.LINEAR : this.gl.LINEAR_MIPMAP_LINEAR);
        }
        this.hd = hd;
      }'''
    return "import {drawingSize} from './render-quality.js';\n" + replace_once(text, before, after)


if __name__ == '__main__':
    path = ROOT / 'companion/avatar_web/vendor/mesh-avatar.js'
    path.write_bytes(patch(path.read_bytes()))
