"""Install optional, hash-checked local rendering libraries, without changing Python dependencies."""

import hashlib
from pathlib import Path
import sys

import httpx


ROOT = Path(__file__).resolve().parent.parent
DESTINATION = ROOT / '.cache/avatar-runtimes/live2d'
SOURCES = {
    'live2dcubismcore.min.js': (
        'https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js',
        '25ae938cb4fe282ce189b357bcc97e603d1e1f7ec78bf04150d401c23cdc792f'),
    'pixi.min.js': (
        'https://cdn.jsdelivr.net/npm/pixi.js@6.5.10/dist/browser/pixi.min.js',
        '403f2f2ee8145fa17f60c5c89403056efe2680e5096ec2762036486914ed19c5'),
    'cubism4.min.js': (
        'https://cdn.jsdelivr.net/npm/pixi-live2d-display@0.4.0/dist/cubism4.min.js',
        'af1267e6d52759b245766c578d905bfa025b532d5c3cc727c370957c4409e21b'),
    'unsafe-eval.min.js': (
        'https://cdn.jsdelivr.net/npm/@pixi/unsafe-eval@6.5.10/dist/browser/unsafe-eval.min.js',
        '94bb4bfdbd015087772ee03bc4117e253c326e8ca73a61646bd331b22f6847ad'),
    'pixi-LICENSE.txt': (
        'https://cdn.jsdelivr.net/npm/pixi.js@6.5.10/LICENSE',
        '536a16e090f0b6c1454a7c0b47ee8414a39a2f1724a154f10ca1edc750a2dcfd'),
    'pixi-live2d-display-LICENSE.txt': (
        'https://cdn.jsdelivr.net/npm/pixi-live2d-display@0.4.0/LICENSE',
        '8ccace668a041e78ed525d091b0b5daf8b623ff447f912616de535415e4f302f'),
}


def main():
    DESTINATION.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=45, follow_redirects=True) as client:
        for name, (url, expected) in SOURCES.items():
            path = DESTINATION / name
            if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
                print(name + ': already installed')
                continue
            response = client.get(url)
            response.raise_for_status()
            data = response.content
            if len(data) > 2 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != expected:
                raise ValueError('The downloaded runtime changed: ' + name + '. Update the pinned source after reviewing it.')
            temporary = path.with_suffix(path.suffix + '.download')
            temporary.write_bytes(data)
            temporary.replace(path)
            print(name + ': installed')
    (DESTINATION / 'NOTICE.txt').write_text(
        'Live2D Cubism Core 5.1.0: Live2D Inc. Proprietary Software License.\n'
        'https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_en.html\n'
        'PixiJS 6.5.10 and @pixi/unsafe-eval 6.5.10: MIT.\n'
        'pixi-live2d-display 0.4.0: MIT.\n'
        'Source URLs and SHA-256 hashes: scripts/setup_live2d.py.\n'
        'These optional runtime files are local cache assets, excluded from Git.\n', encoding='utf-8')
    print('Local Live2D rendering is ready. Imported models keep their own usage terms.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, httpx.HTTPError) as exc:
        print('Live2D setup failed: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
