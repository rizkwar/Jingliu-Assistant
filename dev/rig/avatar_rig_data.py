"""File authoring for Inochi 0.8 INX puppets; independent of the assistant."""
import copy
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import struct

MAGIC = b'TRNSRTS\0'
LIMIT = 128 * 1024 * 1024


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def finite_tree(value):
    if isinstance(value, list):
        return all(finite_tree(v) for v in value)
    return number(value)


def walk(node):
    yield node
    for child in node.get('children', []) or []:
        yield from walk(child)


class RigStore:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError('The authoring root must be an existing directory.')

    def path(self, name, extensions=('.inx', '.inp')):
        if not isinstance(name, str) or not name or any(c in name for c in ('\\', ':', '\0')):
            raise ValueError('Use a relative INX/INP path with forward slashes.')
        relative = PurePosixPath(name)
        if relative.is_absolute() or any(p in ('', '.', '..') for p in name.split('/')):
            raise ValueError('Path must stay inside the authoring root.')
        target = (self.root / relative).resolve()
        if not target.is_relative_to(self.root) or target.suffix.lower() not in extensions:
            raise ValueError('Only permitted file types inside the authoring root are allowed.')
        return target

    def read(self, name):
        target = self.path(name)
        if target.stat().st_size > LIMIT:
            raise ValueError('Rig exceeds the 128 MiB authoring limit.')
        binary = target.read_bytes()
        if len(binary) < 24 or binary[:8] != MAGIC:
            raise ValueError('Expected an Inochi 0.8 TRNSRTS container.')
        length = struct.unpack_from('>I', binary, 8)[0]
        if length > 24 * 1024 * 1024 or 12 + length + 12 > len(binary):
            raise ValueError('Invalid or oversized JSON section.')
        data = json.loads(binary[12:12 + length], parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON.')))
        tail = binary[12 + length:]
        textures = self.texture_count(tail)
        self.validate_data(data, textures)
        return data, tail

    @staticmethod
    def texture_count(tail):
        if len(tail) < 12 or tail[:8] != b'TEX_SECT':
            raise ValueError('Missing embedded texture section.')
        count = struct.unpack_from('>I', tail, 8)[0]
        if count > 256:
            raise ValueError('Too many texture slots.')
        offset = 12
        for _ in range(count):
            if offset + 5 > len(tail):
                raise ValueError('Truncated texture header.')
            size = struct.unpack_from('>I', tail, offset)[0]
            offset += 5 + size
            if offset > len(tail):
                raise ValueError('Truncated texture payload.')
        if offset < len(tail):
            if tail[offset:offset + 8] != b'EXT_SECT' or offset + 12 > len(tail):
                raise ValueError('Invalid extension section.')
            extensions = struct.unpack_from('>I', tail, offset + 8)[0]
            offset += 12
            if extensions > 256:
                raise ValueError('Too many extension sections.')
            for _ in range(extensions):
                for _ in range(2):  # vendor name, then its opaque payload
                    if offset + 4 > len(tail):
                        raise ValueError('Truncated extension header.')
                    size = struct.unpack_from('>I', tail, offset)[0]
                    offset += 4 + size
                    if offset > len(tail):
                        raise ValueError('Truncated extension payload.')
        if offset != len(tail):
            raise ValueError('Unexpected trailing container data.')
        return count

    @staticmethod
    def validate_data(data, texture_count):
        nodes = list(walk(data['nodes']))
        if len(nodes) > 1000:
            raise ValueError('Too many nodes for this authoring tool.')
        ids = [n['uuid'] for n in nodes]
        params = data.get('param') or []
        ids += [p['uuid'] for p in params]
        if any(type(i) is not int or not 0 <= i < 2**32 for i in ids) or len(set(ids)) != len(ids):
            raise ValueError('Invalid or duplicate UUIDs.')
        by_id = {n['uuid']: n for n in nodes}
        param_by_id={p['uuid']:p for p in params}
        for node in nodes:
            if node['type']!='SimplePhysics':continue
            if type(node.get('param')) is not int or node.get('param') not in param_by_id or node.get('model_type') not in ('Pendulum','SpringPendulum') or node.get('map_mode') not in ('AngleLength','XY','LengthAngle','YX'):
                raise ValueError('Invalid physics driver model, mapping or parameter reference.')
            for key in ('length','frequency','gravity','angle_damping','length_damping'):
                if not number(node.get(key)) or node[key]<0 or (key in ('length','frequency') and node[key]==0):
                    raise ValueError('Invalid physics driver constants.')
            if not isinstance(node.get('output_scale'),list) or len(node['output_scale'])!=2 or not finite_tree(node['output_scale']):
                raise ValueError('Invalid physics output scale.')
            if any(b['node']==node['uuid'] for b in param_by_id[node['param']].get('bindings',[])):
                raise ValueError('Physics parameter cannot drive its own input.')
        for n in nodes:
            if n['type'] != 'Part':
                continue
            m = n['mesh']
            verts, uvs, indices = m['verts'], m['uvs'], m['indices']
            if not verts or len(verts) % 2 or len(uvs) != len(verts) or not finite_tree(verts + uvs):
                raise ValueError('Invalid mesh coordinates or UV count.')
            if len(verts) // 2 >= 65536 or len(indices) % 3 or not indices:
                raise ValueError('Invalid mesh size or triangle list.')
            if any(type(i) is not int or not 0 <= i < len(verts) // 2 for i in indices):
                raise ValueError('Triangle index outside the vertex array.')
            slots = n['textures']
            if len(slots) != 3 or any(type(s) is not int or (s != 2**32-1 and not 0 <= s < texture_count) for s in slots):
                raise ValueError('Invalid texture slot reference.')
            masks=n.get('masks',[])
            if not isinstance(masks,list) or len(masks)>8:
                raise ValueError('Invalid or excessive mask bindings.')
            seen=set()
            for mask in masks:
                source=mask.get('source')
                if type(source) is not int or source not in by_id or by_id[source]['type'] not in ('Part','Composite') or source==n['uuid'] or source in seen:
                    raise ValueError('Invalid, missing or duplicate mask source.')
                if mask.get('mode') not in ('Mask','DodgeMask'):
                    raise ValueError('Unsupported mask binding mode.')
                seen.add(source)
            if not number(n.get('mask_threshold',.5)) or not 0<=n.get('mask_threshold',.5)<=1:
                raise ValueError('Invalid mask threshold.')
        for p in params:
            axes = p['axis_points']
            for a in axes:
                if not a or not finite_tree(a) or any(not 0 <= v <= 1 for v in a) or any(x >= y for x, y in zip(a, a[1:])):
                    raise ValueError('Invalid parameter axis points.')
            if len(axes) != 2 or (not p['is_vec2'] and len(axes[1]) != 1):
                raise ValueError('Invalid parameter dimensionality.')
            for key in ('min', 'max', 'defaults'):
                if len(p[key]) != 2 or not finite_tree(p[key]):
                    raise ValueError('Invalid parameter range/defaults.')
            for i in range(2):
                if p['max'][i] <= p['min'][i] or not p['min'][i] <= p['defaults'][i] <= p['max'][i]:
                    raise ValueError('Default outside parameter range.')
            targets = set()
            for b in p.get('bindings') or []:
                node = by_id.get(b['node'])
                target = (b['node'], b['param_name'])
                if node is None or target in targets:
                    raise ValueError('Missing or duplicate binding target.')
                targets.add(target)
                values, flags = b['values'], b['isSet']
                if len(values) != len(axes[0]) or len(flags) != len(axes[0]):
                    raise ValueError('Binding X dimension mismatch.')
                for row, mask in zip(values, flags):
                    if len(row) != len(axes[1]) or len(mask) != len(axes[1]) or any(type(v) is not bool for v in mask):
                        raise ValueError('Binding Y dimension mismatch.')
                    for value in row:
                        if b['param_name'] == 'deform':
                            if node['type'] != 'Part' or len(value) != len(node['mesh']['verts']) // 2:
                                raise ValueError('Deformation/vertex count mismatch.')
                            if any(len(v) != 2 or not finite_tree(v) for v in value):
                                raise ValueError('Invalid deformation offsets.')
                            RigStore.check_orientation(node['mesh'], value)
                        elif not number(value):
                            raise ValueError('Invalid scalar binding value.')
        animations=data.get('animations') or {}
        if not isinstance(animations,dict) or len(animations)>32:raise ValueError('Invalid or excessive animation clips.')
        for name,clip in animations.items():
            if not isinstance(name,str) or not name or not number(clip.get('timestep')) or not 1/240<=clip['timestep']<=1:
                raise ValueError('Invalid animation name or timestep.')
            length=clip.get('length')
            if type(length) is not int or not 1<=length<=36000 or len(clip.get('lanes',[]))>128:
                raise ValueError('Invalid animation length or lane count.')
            targets=set()
            for lane in clip.get('lanes',[]):
                p=param_by_id.get(lane.get('uuid'));axis=lane.get('target')
                if p is None or type(axis) is not int or not 0<=axis<=(1 if p['is_vec2'] else 0):
                    raise ValueError('Invalid animation parameter or axis reference.')
                if (p['uuid'],axis) in targets:raise ValueError('Duplicate animation lane target.')
                targets.add((p['uuid'],axis))
                if lane.get('interpolation') not in ('Nearest','Stepped','Linear','Cubic','Bezier'):
                    raise ValueError('Unsupported animation interpolation.')
                keys=lane.get('keyframes',[])
                if not 1<=len(keys)<=4000:raise ValueError('Invalid animation keyframe count.')
                previous=-1
                for key in keys:
                    frame=key.get('frame');value=key.get('value');tension=key.get('tension',.5)
                    if type(frame) is not int or not previous<frame<length or not number(value) or not p['min'][axis]<=value<=p['max'][axis] or not number(tension) or not 0<=tension<=1:
                        raise ValueError('Invalid animation keyframe, range or ordering.')
                    previous=frame

    @staticmethod
    def check_orientation(mesh, offsets):
        v = mesh['verts']
        for i in range(0, len(mesh['indices']), 3):
            a, b, c = mesh['indices'][i:i+3]
            def cross(deformed):
                def point(k):
                    return (v[2*k] + (offsets[k][0] if deformed else 0), v[2*k+1] + (offsets[k][1] if deformed else 0))
                aa, bb, cc = point(a), point(b), point(c)
                return (bb[0]-aa[0])*(cc[1]-aa[1])-(bb[1]-aa[1])*(cc[0]-aa[0])
            base, changed = cross(False), cross(True)
            if abs(base) < 1e-9 or base * changed <= 0:
                raise ValueError('A keyform collapses or inverts a mesh triangle.')

    def summary(self, name):
        data, tail = self.read(name)
        nodes = list(walk(data['nodes']))
        return {'file': name, 'format': 'Inochi 0.8', 'textureSlots': self.texture_count(tail),
                'textureSectionSha256': hashlib.sha256(tail).hexdigest(),
                'nodes': [{'uuid': n['uuid'], 'name': n['name'], 'type': n['type'], 'enabled': n.get('enabled', True),
                           **({'vertices': len(n['mesh']['verts'])//2, 'triangles': len(n['mesh']['indices'])//3} if n['type']=='Part' else {})} for n in nodes],
                'parameters': [{'uuid': p['uuid'], 'name': p['name'], 'range': [p['min'], p['max']], 'defaults': p['defaults'],
                                'axisPoints': p['axis_points'], 'bindings': len(p.get('bindings') or [])} for p in data.get('param') or []]}

    def save_new(self, output, data, tail):
        target = self.path(output)
        self.validate_data(data, self.texture_count(tail))
        payload = json.dumps(data, allow_nan=False, separators=(',', ':')).encode('utf8')
        binary = MAGIC + struct.pack('>I', len(payload)) + payload + tail
        if len(binary) > LIMIT or len(payload) > 24 * 1024 * 1024:
            raise ValueError('Output exceeds the authoring size limit.')
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(binary)
        return {'file': output, 'bytes': len(binary), 'sha256': hashlib.sha256(binary).hexdigest(), 'textureSectionSha256': hashlib.sha256(tail).hexdigest()}

    @staticmethod
    def binding(data, parameter, node_uuid, x_index, y_index):
        params = [p for p in data.get('param') or [] if p['name'] == parameter]
        if len(params) != 1:
            raise ValueError('Expected a unique parameter name.')
        bindings = [b for b in params[0].get('bindings') or [] if b['node'] == node_uuid and b['param_name'] == 'deform']
        if len(bindings) != 1:
            raise ValueError('No unique deformation binding for that node.')
        b = bindings[0]
        if type(x_index) is not int or type(y_index) is not int or not 0 <= x_index < len(b['values']) or not 0 <= y_index < len(b['values'][x_index]):
            raise ValueError('Keyform index outside parameter axes.')
        return b

    def keyform(self, name, parameter, node_uuid, x_index, y_index, start=0, count=32):
        data, _ = self.read(name)
        b = self.binding(data, parameter, node_uuid, x_index, y_index)
        offsets = b['values'][x_index][y_index]
        node = next(n for n in walk(data['nodes']) if n['uuid'] == node_uuid)
        if type(start) is not int or start < 0 or type(count) is not int or not 1 <= count <= 64:
            raise ValueError('Use a nonnegative start and count 1..64.')
        return {'node': node['name'], 'vertexCount': len(offsets), 'coordinates': 'node-local pixels; offsets from rest',
                'vertices': [{'index': i, 'rest': node['mesh']['verts'][2*i:2*i+2], 'offset': offsets[i]}
                             for i in range(start, min(start+count, len(offsets)))]}

    def edit_keyform(self, name, output, parameter, node_uuid, x_index, y_index, edits):
        data, tail = self.read(name)
        b = self.binding(data, parameter, node_uuid, x_index, y_index)
        offsets = b['values'][x_index][y_index]
        if not isinstance(edits, list) or not 1 <= len(edits) <= 128:
            raise ValueError('Supply 1..128 vertex edits.')
        seen = set()
        for e in edits:
            i = e['index']
            if type(i) is not int or not 0 <= i < len(offsets) or i in seen:
                raise ValueError('Invalid or duplicate vertex index.')
            seen.add(i)
            if any(not number(e[k]) or abs(e[k]) > 500 for k in ('dx', 'dy')):
                raise ValueError('Offsets must be finite pixels within -500..500.')
            offsets[i] = [e['dx'], e['dy']]
        b['isSet'][x_index][y_index] = True
        return self.save_new(output, data, tail)

    def set_defaults(self, name, output, values):
        data, tail = self.read(name)
        if not isinstance(values, dict) or not values:
            raise ValueError('Supply parameter names mapped to [x,y] defaults.')
        for key, value in values.items():
            matches = [p for p in data.get('param') or [] if p['name'] == key]
            if len(matches) != 1 or not isinstance(value, list) or len(value) != 2 or not finite_tree(value):
                raise ValueError('Invalid parameter name or default pair.')
            if not matches[0]['is_vec2'] and value[1] != 0:
                raise ValueError('A 1D parameter must have Y=0.')
            matches[0]['defaults'] = copy.deepcopy(value)
        return self.save_new(output, data, tail)
