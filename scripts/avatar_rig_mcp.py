"""Small, local STDIO MCP for saved avatar rigs. Does not control desktop UI."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from avatar_rig_data import RigStore


def create_server(root, node_command='node'):
    store = RigStore(root)
    server = FastMCP('Avatar Rig Files', instructions='Edit saved Inochi 0.8 rigs inside the configured artwork root. '
                     'This is a file authoring server, not a live Inochi Creator bridge. '
                     'Always save to a new filename. Geometry validation does not prove visual quality. '
                     'Only request vertex arrays when needed; inspect returns concise summaries.', log_level='WARNING')
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
    write = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)

    @server.tool(annotations=read)
    def rig_status() -> dict:
        """Report supported file tools, unavailable live controls, and rig-builder availability."""
        return {'mode': 'local file authoring', 'format': 'Inochi 0.8 INX/INP', 'transport': 'stdio',
                'nodeAvailable': shutil.which(node_command) is not None,
                'liveEditorControl': False, 'renderPreview': 'software inspection contact sheets', 'networkRequired': False,
                'writes': 'new checkpoint files only', 'visualReviewRequired': True}

    @server.tool(annotations=read)
    def rig_list_files() -> list[str]:
        """List local saved rigs under the permitted artwork folder."""
        return sorted(p.relative_to(store.root).as_posix() for p in store.root.rglob('*')
                      if p.is_file() and p.suffix.lower() in ('.inx', '.inp') and p.resolve().is_relative_to(store.root))[:200]

    @server.tool(annotations=read)
    def rig_inspect(file: str) -> dict:
        """Read part IDs, mesh counts, parameter ranges/defaults and texture hash; omit large vertex arrays."""
        return store.summary(file)

    @server.tool(annotations=read)
    def rig_validate(file: str) -> dict:
        """Check container bounds, UUIDs, mesh/UV/index counts, bindings and triangle winding at saved keyforms."""
        data, tail = store.read(file)
        return {'valid': True, 'file': file, 'textureSlots': store.texture_count(tail),
                'parameters': len(data.get('param') or []),
                'limits': 'Saved keyforms checked; combined poses, artwork overlaps and animation quality need separate review.'}

    @server.tool(annotations=write)
    def rig_build_jingliu(source: str, output: str) -> dict:
        """Build head XY, tilt and manual hair-sway keyforms from the saved 23-part Jingliu PSD import."""
        store.read(source)
        destination = store.path(output)
        if destination.exists():
            raise ValueError('Choose a new output filename.')
        node = shutil.which(node_command)
        if node is None:
            raise ValueError('Node.js is required for the bundled rig builder.')
        builder = Path(__file__).with_name('build_inochi_jingliu.mjs')
        result = subprocess.run([node, str(builder), str(store.path(source)), str(destination)],
                                capture_output=True, text=True, timeout=60, check=False, shell=False)
        if result.returncode:
            raise ValueError('Rig builder failed: ' + result.stderr[-1500:])
        summary = store.summary(output)
        return {'file': output, 'parts': len(summary['nodes'])-1, 'parameters': summary['parameters'],
                'textureSectionSha256': summary['textureSectionSha256']}

    @server.tool(annotations=read)
    def rig_get_keyform(file: str, parameter: str, node_uuid: int, x_index: int, y_index: int,
                        start: int = 0, count: int = 32) -> dict:
        """Read at most 64 rest vertices and offsets from one part/keyform, using zero-based indices."""
        return store.keyform(file, parameter, node_uuid, x_index, y_index, start, count)

    @server.tool(annotations=write)
    def rig_edit_keyform(file: str, output: str, parameter: str, node_uuid: int, x_index: int,
                         y_index: int, edits: list[dict]) -> dict:
        """Save a new rig with offsets replaced for up to 128 vertices: edits=[{index,dx,dy}]. Reject flipped triangles."""
        return store.edit_keyform(file, output, parameter, node_uuid, x_index, y_index, edits)

    @server.tool(annotations=write)
    def rig_set_defaults(file: str, output: str, values: dict[str, list[float]]) -> dict:
        """Save a new pose checkpoint with parameter defaults {name:[x,y]}; reopening it in Creator shows that pose."""
        return store.set_defaults(file, output, values)

    def render_request(request):
        workspace = Path(__file__).resolve().parent.parent
        python = workspace/'.venv/Scripts/python.exe'
        if not python.is_file():
            raise ValueError('The project Python environment with PySide6 is needed for previews and texture import.')
        request['root'] = str(store.root)
        result = subprocess.run([str(python), str(Path(__file__).with_name('render_inochi_rig.py'))],
                                input=json.dumps(request), capture_output=True, text=True,
                                timeout=180 if request.get('mode')=='motion_preview' else 90, shell=False)
        if result.returncode:
            raise ValueError('Inspection renderer failed: ' + result.stderr[-1500:])
        return json.loads(result.stdout)

    @server.tool(annotations=write)
    def rig_render_preview(file: str, output: str, poses: list[dict], size: int = 512,
                           region: list[int] | None = None) -> dict:
        """Render 1..12 saved-mesh poses to a new PNG. poses=[{label,values:{parameter:[x,y]}}]; optional region=[x,y,width,height] in the 1254px artwork. Not a live runtime."""
        store.read(file)
        store.path(output, extensions=('.png',))
        return render_request({'file': file, 'output': output, 'poses': poses, 'size': size,'region':region})

    @server.tool(annotations=write)
    def rig_build_jingliu_eyes(file: str, output: str, manifest: str) -> dict:
        """Add separated iris/lid meshes, clipping, independent blinks and gaze to the 23-part head rig. Manifest maps L/R component names to PhotoCraft PNGs."""
        store.read(file)
        target=store.path(output)
        if target.exists():raise ValueError('Choose a new output filename.')
        store.path(manifest,extensions=('.json',))
        return render_request({'mode':'eyes','file':file,'output':output,'manifest':manifest})

    @server.tool(annotations=write)
    def rig_build_jingliu_mouth(file: str, output: str, manifest: str) -> dict:
        """Add separated lips, cavity, teeth, tongue, opening/form controls and subtle jaw deformation to the 29-part eye rig. Import five PhotoCraft PNGs via a scoped manifest."""
        store.read(file)
        if store.path(output).exists():raise ValueError('Choose a new output filename.')
        store.path(manifest,extensions=('.json',))
        return render_request({'mode':'mouth','file':file,'output':output,'manifest':manifest})

    @server.tool(annotations=write)
    def rig_add_idle_motion(file: str, output: str) -> dict:
        """Add native blink/head animation clips and a damped hair pendulum to the 34-part mouth checkpoint. Textures and existing keyforms are retained."""
        store.read(file)
        if store.path(output).exists():raise ValueError('Choose a new output filename.')
        return render_request({'mode':'idle','file':file,'output':output})

    @server.tool(annotations=write)
    def rig_render_motion_preview(file: str, output: str, animation: str = 'Idle - blink and hair',
                                   seconds: float = 6, fps: int = 30, size: int = 512, physics: bool = True) -> dict:
        """Render a 2..12-second MP4 inspection preview of saved motion/pendulum data, with optional physics comparison. Requires local FFmpeg; not an Inochi runtime recording."""
        store.read(file)
        store.path(output,extensions=('.mp4',))
        return render_request({'mode':'motion_preview','file':file,'output':output,'animation':animation,
                               'seconds':seconds,'fps':fps,'size':size,'physics':physics})

    @server.tool(annotations=write)
    def rig_replace_texture(file: str, output: str, node_uuid: int, png: str) -> dict:
        """Import a full-canvas 1254x1254 PNG edited in PhotoCraft into one part's texture; save a new rig. Other textures are preserved."""
        store.read(file)
        store.path(output)
        path = store.path(png, extensions=('.png',))
        if path.stat().st_size > 16*1024*1024:
            raise ValueError('Replacement texture is too large.')
        return render_request({'mode': 'texture', 'file': file, 'output': output, 'node_uuid': node_uuid, 'png': png})

    return server


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, help='Only this avatar-authoring folder is accessible.')
    parser.add_argument('--node', default='node', help='Node executable for the fixed bundled builder.')
    args = parser.parse_args()
    create_server(args.root, args.node).run(transport='stdio')
