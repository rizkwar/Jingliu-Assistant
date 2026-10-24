"""Per-character visual models. Imported art stays in ignored local data."""

from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

from .character import character_key
from .config import PROJECT_ROOT


MAX_FILE = 64 * 1024 * 1024
MAX_BUNDLE = 256 * 1024 * 1024
CURRENT_MODEL = {'id': 'current', 'name': 'AI portrait (current)', 'kind': 'mesh'}


def _relative(value):
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise ValueError('Invalid Live2D resource path.')
    value = value.replace('\\', '/')
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {'..', '.'} for part in value.split('/')) or ':' in value or '\x00' in value:
        raise ValueError('Live2D resources must use relative paths inside the model folder.')
    return path.as_posix()


def _json(raw):
    if len(raw) > 1024 * 1024:
        raise ValueError('Live2D JSON is too large.')
    try:
        return json.loads(raw.decode('utf-8-sig'))
    except (UnicodeError, ValueError):
        raise ValueError('Could not read Live2D JSON.') from None


def _definition(document):
    """Keep rig resources, excluding prerecorded sounds and automatic motions."""
    if not isinstance(document, dict) or document.get('Version') != 3:
        raise ValueError('Choose a Cubism .model3.json model or a ZIP containing one.')
    refs = document.get('FileReferences', {})
    if not isinstance(refs, dict) or not isinstance(refs.get('Textures'), list) or not 1 <= len(refs['Textures']) <= 16:
        raise ValueError('The Live2D model needs a moc3 and 1 to 16 textures.')
    clean = {'Moc': _relative(refs.get('Moc')), 'Textures': [_relative(p) for p in refs['Textures']]}
    if not clean['Moc'].lower().endswith('.moc3'):
        raise ValueError('The model must reference a .moc3 rig.')
    if any(Path(p).suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp'} for p in clean['Textures']):
        raise ValueError('Live2D textures must be PNG, JPEG, or WebP images.')
    for key in ('Physics', 'Pose', 'DisplayInfo'):
        if refs.get(key):
            clean[key] = _relative(refs[key])
            if not clean[key].lower().endswith('.json'):
                raise ValueError('Live2D rig metadata must be JSON.')
    result = {'Version': 3, 'FileReferences': clean}
    # No motions, audio, expressions, custom scripts or external URLs are loaded.
    return result


def _resource_paths(document):
    refs = document['FileReferences']
    return [refs['Moc'], *refs['Textures'], *(refs[k] for k in ('Physics', 'Pose', 'DisplayInfo') if k in refs)]


def _read_folder(source):
    folder = source.parent.resolve()
    def read(name):
        path = (folder / _relative(name)).resolve()
        if not path.is_relative_to(folder) or not path.is_file() or path.stat().st_size > MAX_FILE:
            raise ValueError('A Live2D resource is missing, outside its folder, or too large.')
        return path.read_bytes()
    return _json(read(source.name)), read


def _zip_aliases(archive):
    aliases = {}
    for member in archive.infolist():
        if member.is_dir():
            continue
        name = _relative(member.filename)
        # Some Chinese ZIPs omit the UTF-8 flag. Resolve their legacy GBK names
        # against the manifest without ever extracting archive-provided paths.
        names = {name}
        if not member.flag_bits & 0x800:
            for encoding in ('utf-8', 'gb18030', 'shift_jis'):
                try:
                    names.add(_relative(name.encode('cp437').decode(encoding)))
                except (UnicodeError, ValueError):
                    pass
        for alias in names:
            if alias in aliases and aliases[alias] != member:
                raise ValueError('The ZIP has ambiguous resource names.')
            aliases[alias] = member
    return aliases


def live2d_bundle(source):
    """Validate and return a self-contained, ASCII-named rig asset dictionary."""
    source = Path(source)
    archive = None
    try:
        if source.suffix.lower() == '.zip':
            archive = zipfile.ZipFile(source)
            if len(archive.infolist()) > 2048 or sum(m.file_size for m in archive.infolist()) > MAX_BUNDLE:
                raise ValueError('The model ZIP is too large.')
            aliases = _zip_aliases(archive)
            entries = [m for m in archive.infolist() if m.filename.lower().endswith('.model3.json')]
            if len(entries) != 1:
                raise ValueError('This ZIP needs exactly one .model3.json. Extract it and choose the desired model file instead.')
            # Match a recovered directory spelling as well as the raw ZIP name.
            roots = {PurePosixPath(n).parent for n, m in aliases.items() if m == entries[0]}
            def read(name):
                name = _relative(name)
                member = next((aliases.get((root / name).as_posix()) for root in roots
                               if (root / name).as_posix() in aliases), None)
                if member is None or member.file_size > MAX_FILE:
                    raise ValueError('A required Live2D resource is missing or too large.')
                return archive.read(member)
            document = _json(archive.read(entries[0]))
        elif source.name.lower() == 'model3.json' or source.name.lower().endswith('.model3.json'):
            document, read = _read_folder(source)
        else:
            raise ValueError('Choose a Live2D ZIP or .model3.json file.')
        clean = _definition(document)
        resources, renamed = {}, {}
        for name in _resource_paths(clean):
            body = read(name)
            if name == clean['FileReferences']['Moc'] and not body.startswith(b'MOC3'):
                raise ValueError('The moc3 rig is invalid.')
            if name.lower().endswith('.json'):
                if not isinstance(_json(body), dict):
                    raise ValueError('Live2D rig metadata must be a JSON object.')
            target = 'assets/' + hashlib.sha256(body).hexdigest()[:24] + Path(name).suffix.lower()
            resources[target] = body
            renamed[name] = target
        if sum(map(len, resources.values())) > MAX_BUNDLE:
            raise ValueError('The Live2D model is too large.')
        refs = clean['FileReferences']
        for key, value in tuple(refs.items()):
            refs[key] = [renamed[p] for p in value] if key == 'Textures' else renamed[value]
        resources['model3.json'] = json.dumps(clean, ensure_ascii=True).encode('utf-8')
        return resources
    except (zipfile.BadZipFile, KeyError, RuntimeError):
        raise ValueError('Could not read this Live2D model package.') from None
    finally:
        if archive is not None:
            archive.close()


class AvatarModels:
    def __init__(self, root=PROJECT_ROOT):
        self.root = Path(root).resolve()
        self.directory = self.root / 'data/avatar_models'
        self.path = self.root / 'data/avatar_models.json'

    def _load(self):
        if not self.path.exists():
            return {'version': 1, 'characters': {}}
        try:
            if self.path.stat().st_size > 1024 * 1024:
                raise ValueError()
            document = json.loads(self.path.read_text(encoding='utf-8'))
            if document.get('version') != 1 or not isinstance(document.get('characters'), dict):
                raise ValueError()
            if any(not isinstance(value, dict) for value in document['characters'].values()):
                raise ValueError()
            return document
        except (ValueError, AttributeError):
            raise ValueError('Could not read local avatar models. Check data/avatar_models.json.') from None

    def _save(self, document):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent, suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(document, stream, ensure_ascii=True, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def models(self, profile):
        record = self._load()['characters'].get(character_key(profile), {})
        models = record.get('models', [])
        if not isinstance(models, list) or len(models) > 64:
            raise ValueError('Invalid avatar model list.')
        for model in models:
            if (not isinstance(model, dict) or model.get('kind') not in {'live2d', 'layered'}
                    or not isinstance(model.get('name'), str) or not 1 <= len(model['name']) <= 120
                    or not isinstance(model.get('id'), str)
                    or not model['id'].startswith(model['kind'] + '-')
                    or len(model['id']) != len(model['kind']) + 17
                    or any(c not in '0123456789abcdef' for c in model['id'][len(model['kind']) + 1:])):
                raise ValueError('Invalid avatar model entry.')
            if model.get('framing', 'portrait') not in {'portrait', 'full'}:
                raise ValueError('Invalid model framing.')
            appearance = model.get('appearance', {})
            if (not isinstance(appearance, dict) or len(appearance) > 32
                    or any(not isinstance(k, str) or not 1 <= len(k) <= 80 or type(v) not in {int, float}
                           or not math.isfinite(v) or abs(v) > 10000 for k, v in appearance.items())):
                raise ValueError('Invalid model appearance controls.')
            if not isinstance(model.get('credit', ''), str) or len(model.get('credit', '')) > 2000:
                raise ValueError('Invalid model credits.')
            if (not isinstance(model.get('blindfold_parameter', ''), str)
                    or len(model.get('blindfold_parameter', '')) > 80
                    or type(model.get('blindfold', False)) is not bool):
                raise ValueError('Invalid model accessory control.')
        return [dict(CURRENT_MODEL), *deepcopy(models)]

    def selected(self, profile):
        selected = self._load()['characters'].get(character_key(profile), {}).get('selected', 'current')
        return next((m for m in self.models(profile) if m['id'] == selected), dict(CURRENT_MODEL))

    def select(self, profile, model_id):
        if model_id not in {m['id'] for m in self.models(profile)}:
            raise ValueError('Choose an installed model for this character.')
        document = self._load()
        record = document['characters'].setdefault(character_key(profile), {'models': []})
        record['selected'] = model_id
        self._save(document)

    def set_framing(self, profile, model_id, framing):
        if framing not in {'portrait', 'full'}:
            raise ValueError('Choose portrait or full-model framing.')
        self.models(profile)  # Validate existing records before modifying them.
        document = self._load()
        for model in document['characters'].get(character_key(profile), {}).get('models', []):
            if model['id'] == model_id:
                model['framing'] = framing
                self._save(document)
                return
        raise ValueError('Choose an installed Live2D model.')

    def set_blindfold(self, profile, model_id, enabled):
        self.models(profile)
        document = self._load()
        for model in document['characters'].get(character_key(profile), {}).get('models', []):
            parameter = model.get('blindfold_parameter')
            if model['id'] == model_id and parameter:
                model['blindfold'] = bool(enabled)
                model['appearance'] = {parameter: 0 if enabled else 1}
                self._save(document)
                return model
        raise ValueError('This model has no configured blindfold control.')

    def model_path(self, model):
        filename = 'layered.json' if model['kind'] == 'layered' else 'model3.json'
        path = (self.directory / model['id'] / filename).resolve()
        if not path.is_relative_to(self.directory.resolve()):
            raise ValueError('Invalid installed model path.')
        return path

    def import_layered(self, profile, source, name='AI layered rig (experimental)'):
        from .layered_assets import layered_bundle
        if not profile or not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
            raise ValueError('Choose a character and a short model name.')
        resources = layered_bundle(source)
        fingerprint = hashlib.sha256()
        for filename, body in sorted(resources.items()):
            fingerprint.update(filename.encode())
            fingerprint.update(body)
        model_id = 'layered-' + fingerprint.hexdigest()[:16]
        target = self.directory / model_id
        if not target.resolve().is_relative_to(self.directory.resolve()):
            raise ValueError('Invalid local model destination.')
        for filename, body in resources.items():
            path = target / filename
            if not path.resolve().is_relative_to(target.resolve()):
                raise ValueError('Invalid model resource destination.')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        document = self._load()
        record = document['characters'].setdefault(character_key(profile), {'models': [], 'selected': 'current'})
        model = {'id': model_id, 'name': name.strip(), 'kind': 'layered',
                 'credit': 'AI v5 artwork with separate head, neck, hair and earring layers. Experimental 2.5D depth rig.'}
        record['models'] = [m for m in self.models(profile)[1:] if m['id'] != model_id] + [model]
        self._save(document)
        return model

    def import_live2d(self, profile, source, name='Live2D rig (experimental)', *, credit='', blindfold_parameter=''):
        if not profile:
            raise ValueError('Select a character before importing a visual model.')
        if not name.strip() or len(name) > 120 or len(credit) > 2000:
            raise ValueError('Use a model name under 120 characters and credits under 2,000.')
        if not isinstance(blindfold_parameter, str) or len(blindfold_parameter) > 80:
            raise ValueError('Invalid accessory parameter ID.')
        resources = live2d_bundle(source)
        fingerprint = hashlib.sha256()
        for filename, body in sorted(resources.items()):
            fingerprint.update(filename.encode())
            fingerprint.update(body)
        model_id = 'live2d-' + fingerprint.hexdigest()[:16]
        target = self.directory / model_id
        if not target.resolve().is_relative_to(self.directory.resolve()):
            raise ValueError('The model destination is outside the local model library.')
        # Immutable, content-addressed files. A failed import never changes the selection.
        for filename, body in resources.items():
            path = target / filename
            if not path.resolve().is_relative_to(target.resolve()):
                raise ValueError('The model resource destination is outside its folder.')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        document = self._load()
        record = document['characters'].setdefault(character_key(profile), {'models': [], 'selected': 'current'})
        model = {'id': model_id, 'name': name.strip(), 'kind': 'live2d', 'credit': credit}
        if blindfold_parameter:
            model.update(blindfold_parameter=blindfold_parameter, blindfold=False, appearance={blindfold_parameter: 1})
        record['models'] = [m for m in self.models(profile)[1:] if m['id'] != model_id] + [model]
        self._save(document)
        return model
