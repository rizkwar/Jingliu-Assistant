"""Read only the explicitly referenced images of a local layered avatar."""
import json
import math
from pathlib import Path, PurePosixPath

REQUIRED_TEXTURES = {'source', 'base', 'hairmask', 'underpaint', 'backhair', 'eye0_ball', 'eye1_ball',
                     'eyes_closed_0', 'eyes_closed_1', 'eyes_half_0', 'eyes_half_1',
                     'mouth_a', 'mouth_a_half', 'mouth_i'}


def layered_bundle(source):
    source = Path(source).resolve()
    if source.stat().st_size > 65536:
        raise ValueError('Layered rig description is too large.')
    try:
        document = json.loads(source.read_text(encoding='utf-8'))
        if document.get('format') != 'assistant-layered' or document.get('version') != 1:
            raise ValueError()
        if document.get('size') != [1254, 1254]:
            raise ValueError()
        textures = document['textures']
        if not isinstance(textures, dict) or not 4 <= len(textures) <= 32:
            raise ValueError()
        if not REQUIRED_TEXTURES <= textures.keys():
            raise ValueError()
        def numeric(value, depth=0):
            if depth > 8:
                raise ValueError()
            if isinstance(value, dict):
                return all(numeric(v, depth + 1) for v in value.values())
            if isinstance(value, list):
                return len(value) <= 256 and all(numeric(v, depth + 1) for v in value)
            return type(value) in {float, int} and math.isfinite(value) and abs(value) <= 10000
        if not numeric(document['eyes']) or len(document['eyes']) != 2:
            raise ValueError()
        if not numeric(document['rects']) or not numeric(document['underpaintOffset']):
            raise ValueError()
        for eye in document['eyes']:
            if not (0 <= eye['x0'] < eye['x1'] <= 1254 and 2 <= len(eye['top']) == len(eye['bot']) <= 256):
                raise ValueError()
        if len(document['underpaintOffset']) != 2:
            raise ValueError()
        if not REQUIRED_TEXTURES.difference({'source', 'base', 'hairmask', 'underpaint', 'backhair'}) <= document['rects'].keys():
            raise ValueError()
        for rect in document['rects'].values():
            if len(rect) != 4 or any(v < 0 or v > 1254 for v in rect) or rect[2] <= 0 or rect[3] <= 0:
                raise ValueError()
        resources = {}
        for key, name in textures.items():
            if not isinstance(key, str) or len(key) > 64 or not isinstance(name, str):
                raise ValueError()
            path = PurePosixPath(name)
            if (path.is_absolute() or ':' in name or '\\' in name or '\x00' in name
                    or any(p in {'.', '..', ''} for p in name.split('/')) or path.suffix != '.png'):
                raise ValueError()
            local = (source.parent / name).resolve()
            if not local.is_relative_to(source.parent) or local.stat().st_size > 16 * 1024 * 1024:
                raise ValueError()
            body = local.read_bytes()
            if not body.startswith(b'\x89PNG\r\n\x1a\n'):
                raise ValueError()
            width = int.from_bytes(body[16:20], 'big')
            height = int.from_bytes(body[20:24], 'big')
            if not 0 < width <= 4096 or not 0 < height <= 4096:
                raise ValueError()
            resources[name] = body
        if sum(map(len, resources.values())) > 64 * 1024 * 1024:
            raise ValueError()
        resources['layered.json'] = json.dumps(document, ensure_ascii=True, allow_nan=False).encode()
        return resources
    except (KeyError, TypeError, AttributeError, ValueError, OverflowError):
        raise ValueError('Invalid layered avatar. Rebuild it with dev/build_layered_jingliu.py.') from None
