"""Local character assignments and a read-only, allowlisted avatar asset service."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from threading import Thread

from .character import character_key
from .config import PROJECT_ROOT


def assigned_avatar(profile, root=PROJECT_ROOT):
    """Return an explicit assignment, never infer a rig from a character's name."""
    mapping = root / "data/avatars.json"
    if not mapping.exists():
        return None
    try:
        if mapping.stat().st_size > 65536:
            raise ValueError()
        entries = json.loads(mapping.read_text(encoding="utf-8-sig"))["characters"]
        for character, avatar in entries.items():
            if character_key(str(root / character)) == character_key(profile):
                return (root / avatar).resolve()
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        raise ValueError("Avatar assignments could not be read. Check data/avatars.json.") from None
    return None


class AvatarAssets:
    def __init__(self, avatar, root=PROJECT_ROOT, bridge_script=b'', *, kind='mesh'):
        web = root / "companion/avatar_web"
        paths = {
            "index.html": (web / "index.html", "text/html; charset=utf-8"),
            "viewer.js": (web / "viewer.js", "text/javascript; charset=utf-8"),
            "conversation-state.js": (web / "conversation-state.js", "text/javascript; charset=utf-8"),
            "render-quality.js": (web / "render-quality.js", "text/javascript; charset=utf-8"),
            "render-cadence.js": (web / "render-cadence.js", "text/javascript; charset=utf-8"),
            "assistant-motion.js": (web / "assistant-motion.js", "text/javascript; charset=utf-8"),
            "avatar-life.js": (web / "avatar-life.js", "text/javascript; charset=utf-8"),
            "motion-preview.js": (web / "motion-preview.js", "text/javascript; charset=utf-8"),
            "idle-attention.js": (web / "idle-attention.js", "text/javascript; charset=utf-8"),
            "stable-step.js": (web / "stable-step.js", "text/javascript; charset=utf-8"),
            "style.css": (web / "style.css", "text/css; charset=utf-8"),
            "mesh-avatar.js": (web / "vendor/mesh-avatar.js", "text/javascript; charset=utf-8"),
        }
        assets = {'qwebchannel.js': (bridge_script, 'text/javascript; charset=utf-8'),
                  'renderer.json': (json.dumps({'kind': kind}).encode(), 'application/json')}
        if kind == 'mesh':
            paths['avatar.mavatar'] = (Path(avatar), 'application/octet-stream')
        elif kind == 'layered':
            from .layered_assets import layered_bundle
            for name in ('layered-avatar.js', 'layered-rig.js', 'live2d-rig.js', 'rig-preview.js'):
                paths[name] = (web / name, 'text/javascript; charset=utf-8')
            for name, body in layered_bundle(avatar).items():
                assets['model/' + name] = (body, 'image/png' if name.endswith('.png') else 'application/json')
        elif kind == 'live2d':
            from .avatar_models import live2d_bundle
            for name in ('live2d-avatar.js', 'live2d-rig.js', 'live2d-physics.js', 'rig-preview.js'):
                paths[name] = (web / name, 'text/javascript; charset=utf-8')
            runtime = root / '.cache/avatar-runtimes/live2d'
            for name in ('pixi.min.js', 'unsafe-eval.min.js', 'cubism4.min.js', 'live2dcubismcore.min.js'):
                paths['runtime/' + name] = (runtime / name, 'text/javascript; charset=utf-8')
            types = {'.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg',
                     '.jpeg': 'image/jpeg', '.webp': 'image/webp'}
            for name, body in live2d_bundle(avatar).items():
                assets['model/' + name] = (body, types.get(Path(name).suffix, 'application/octet-stream'))
        else:
            raise ValueError('Unsupported avatar renderer.')
        for name, (path, mime) in paths.items():
            if not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
                raise ValueError("Avatar files are missing or too large. See Troubleshooting in README.md.")
            assets[name] = (path.read_bytes(), mime)
        self.prefix = "/" + secrets.token_urlsafe(24) + "/"
        prefix = self.prefix

        class Handler(BaseHTTPRequestHandler):
            def do_GET(handler):
                host = f"127.0.0.1:{handler.server.server_port}"
                name = handler.path.removeprefix(prefix)
                asset = assets.get(name) if handler.path.startswith(prefix) else None
                if handler.headers.get("Host") != host or asset is None:
                    handler.send_error(404)
                    return
                body, mime = asset
                handler.send_response(200)
                handler.send_header("Content-Type", mime)
                handler.send_header("Content-Length", str(len(body)))
                handler.send_header("Cache-Control", "no-store")
                handler.send_header("X-Content-Type-Options", "nosniff")
                handler.send_header("Referrer-Policy", "no-referrer")
                handler.send_header("Permissions-Policy", "microphone=(), camera=(), geolocation=()")
                wasm = " 'wasm-unsafe-eval'" if kind == 'live2d' else ''
                handler.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'" + wasm + "; style-src 'self'; connect-src 'self' blob:; img-src 'self' blob: data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
                handler.end_headers()
                handler.wfile.write(body)

            def log_message(handler, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_port}{prefix}index.html"
        self.thread = Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)
