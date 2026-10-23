"""Apply the two local HD changes to the pinned mesh-avatar 0.2.1 browser build."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PINNED_SHA256 = '691301e4a2a89779617de4f4bf6c407c3003dc27161f5e4a3665566dfcff8e87'


def patch(source):
    if hashlib.sha256(source).hexdigest() != PINNED_SHA256:
        raise ValueError('Expected the original pinned runtime; review upstream changes before patching.')
    text = source.decode('utf-8')
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
    if text.count(before) != 1:
        raise ValueError('Pinned renderer resize function did not match.')
    return ("import {drawingSize} from './render-quality.js';\n" + text.replace(before, after)).encode('utf-8')


if __name__ == '__main__':
    path = ROOT / 'companion/avatar_web/vendor/mesh-avatar.js'
    path.write_bytes(patch(path.read_bytes()))
