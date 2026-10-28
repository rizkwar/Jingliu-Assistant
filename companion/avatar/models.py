"""Per-character visual models. Imported art stays in ignored local data."""

from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

from ..character.profile import character_key
from ..core.config import PROJECT_ROOT


MAX_FILE = 64 * 1024 * 1024
MAX_BUNDLE = 256 * 1024 * 1024
CURRENT_MODEL = {'id': 'current', 'name': 'AI portrait (current)', 'kind': 'mesh'}
# Must match accessories.js.
GLASSES = {'style': ('teacher', 'round', 'rectangle', 'oval', 'halfrim'),
           'frame': ('silver', 'gold', 'black', 'ice', 'crimson'),
           'lens': ('clear', 'moon', 'rose', 'dark')}


FIT = {'scale': (.7, 1.4), 'x': (-.5, .5), 'y': (-.5, .5)}  # Nudging an outfit into place.


def _outfit_id(value):
    return isinstance(value, str) and len(value) == 16 and all(c in '0123456789abcdef' for c in value)


def accessories(values):
    """Checked accessories: {"glasses": {"on": bool, "style", "frame", "lens"}, "outfit": id or ""};
    ValueError otherwise."""
    if not isinstance(values, dict) or values.keys() - {'glasses', 'outfit'}:
        raise ValueError('Invalid model accessories.')
    result = {}
    glasses = values.get('glasses')
    if glasses is not None:
        if (not isinstance(glasses, dict) or glasses.keys() - {'on', *GLASSES} or type(glasses.get('on', False)) is not bool
                or any(glasses.get(key, options[0]) not in options for key, options in GLASSES.items())):
            raise ValueError('Invalid glasses settings.')
        result['glasses'] = {'on': glasses.get('on', False),
                             **{key: glasses.get(key, options[0]) for key, options in GLASSES.items()}}
    outfit = values.get('outfit', '')
    if outfit != '' and not _outfit_id(outfit):
        raise ValueError('Invalid outfit choice.')
    if outfit:
        result['outfit'] = outfit
    return result


def outfits(values):
    """Checked outfits of a model: [{"id", "name", "eyes": [[x, y], [x, y]], "fit": {"scale", "x", "y"}}]."""
    if not isinstance(values, list) or len(values) > 32:
        raise ValueError('Invalid outfit list.')
    result = []
    for outfit in values:
        fit = outfit.get('fit', {}) if isinstance(outfit, dict) else None
        eyes = outfit.get('eyes') if isinstance(outfit, dict) else None
        if (not isinstance(outfit, dict) or outfit.keys() - {'id', 'name', 'eyes', 'fit'} or not _outfit_id(outfit.get('id'))
                or not isinstance(outfit.get('name'), str) or not 1 <= len(outfit['name']) <= 80
                or not isinstance(eyes, list) or len(eyes) != 2
                or any(not isinstance(eye, list) or len(eye) != 2 or any(type(v) not in {int, float} or not math.isfinite(v)
                                                                         or abs(v) > 100000 for v in eye) for eye in eyes)
                or not isinstance(fit, dict) or fit.keys() - FIT.keys()
                or any(type(fit.get(key, 0 if key != 'scale' else 1)) not in {int, float}
                       or not low <= fit.get(key, 0 if key != 'scale' else 1) <= high for key, (low, high) in FIT.items())):
            raise ValueError('Invalid outfit entry.')
        result.append({'id': outfit['id'], 'name': outfit['name'], 'eyes': [list(map(float, eye)) for eye in eyes],
                       'fit': {key: float(fit.get(key, 0 if key != 'scale' else 1)) for key in FIT}})
    return result


def worn(model):
    """What she actually wears: a model's accessories, without glasses while her blindfold is on. The
    outfit comes with what the avatar needs to put it on: its picture and where her eyes are in it."""
    chosen = accessories(model.get('accessories', {}))
    if model.get('blindfold') and chosen.get('glasses', {}).get('on'):
        chosen['glasses'] = {**chosen['glasses'], 'on': False}
    outfit = next((o for o in outfits(model.get('outfits', [])) if o['id'] == chosen.get('outfit')), None)
    chosen.pop('outfit', None)
    if outfit:
        chosen['outfit'] = {'id': outfit['id'], 'url': f"model/outfits/{outfit['id']}.png",
                            'eyes': outfit['eyes'], 'fit': outfit['fit']}
    return chosen


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
            # Entries saved under a character's full path follow it after the project folder moves.
            characters = {}
            for key, value in sorted(document['characters'].items(), key=lambda item: Path(item[0]).is_absolute()):
                characters.setdefault(character_key(key) if Path(key).is_absolute() else key, value)
            document['characters'] = characters
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
            accessories(model.get('accessories', {}))
            outfits(model.get('outfits', []))
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

    def _live2d(self, document, profile, model_id):
        for model in document['characters'].get(character_key(profile), {}).get('models', []):
            if model['id'] == model_id and model['kind'] == 'live2d':
                return model
        raise ValueError('Accessories and outfits are available on Live2D models.')

    def set_accessories(self, profile, model_id, values):
        """What she wears over a Live2D model (glasses, an outfit), remembered with that model. Only the
        given kinds change: setting her glasses keeps her outfit."""
        accessories(values)
        self.models(profile)
        document = self._load()
        model = self._live2d(document, profile, model_id)
        chosen = {**model.get('accessories', {}), **values}  # An outfit of "" takes hers off.
        if chosen.get('outfit') and chosen['outfit'] not in {o['id'] for o in outfits(model.get('outfits', []))}:
            raise ValueError('Choose one of her outfits.')
        model['accessories'] = accessories(chosen)
        self._save(document)
        return model

    def wear_outfit(self, profile, model_id, outfit_id):
        """Puts on one of her outfits, or her own clothes again ("")."""
        self.models(profile)
        document = self._load()
        model = self._live2d(document, profile, model_id)
        if outfit_id and outfit_id not in {o['id'] for o in outfits(model.get('outfits', []))}:
            raise ValueError('Choose one of her outfits.')
        chosen = dict(model.get('accessories', {}))
        chosen.pop('outfit', None)
        if outfit_id:
            chosen['outfit'] = outfit_id
        model['accessories'] = accessories(chosen)
        self._save(document)
        return model

    def add_outfit(self, profile, model_id, picture, name):
        """Makes an outfit from a picture of her wearing it, and puts it on. Raises ValueError when the
        picture cannot be used (see outfits.prepare)."""
        from PySide6.QtGui import QImage
        from .outfits import prepare
        name = ' '.join(str(name).split())[:80] or 'Outfit'
        self.models(profile)
        document = self._load()
        model = self._live2d(document, profile, model_id)
        current = outfits(model.get('outfits', []))
        if len(current) >= 32:
            raise ValueError('She has 32 outfits already. Remove one first.')
        path = Path(picture)
        if not path.is_file() or path.stat().st_size > MAX_FILE:
            raise ValueError('Choose a picture file under 64 MB.')
        texture, eyes = prepare(QImage(str(path)))
        folder = self.directory / model_id / 'outfits'
        folder.mkdir(parents=True, exist_ok=True)
        temporary = folder / 'incoming.png'
        if not texture.save(str(temporary), 'PNG'):
            raise ValueError('The outfit could not be saved.')
        outfit_id = hashlib.sha256(temporary.read_bytes()).hexdigest()[:16]
        os.replace(temporary, folder / f'{outfit_id}.png')
        entry = {'id': outfit_id, 'name': name, 'eyes': [list(eye) for eye in eyes], 'fit': {'scale': 1.0, 'x': 0.0, 'y': 0.0}}
        model['outfits'] = [o for o in current if o['id'] != outfit_id] + [entry]
        model['accessories'] = accessories({**model.get('accessories', {}), 'outfit': outfit_id})
        self._save(document)
        return model

    def fit_outfit(self, profile, model_id, outfit_id, fit):
        """Nudges an outfit into place: {"scale", "x", "y"} (x and y in eye spacings)."""
        self.models(profile)
        document = self._load()
        model = self._live2d(document, profile, model_id)
        current = outfits(model.get('outfits', []))
        for outfit in current:
            if outfit['id'] == outfit_id:
                outfit['fit'] = {**outfit['fit'], **fit}
                model['outfits'] = outfits(current)
                self._save(document)
                return model
        raise ValueError('Choose one of her outfits.')

    def remove_outfit(self, profile, model_id, outfit_id):
        self.models(profile)
        document = self._load()
        model = self._live2d(document, profile, model_id)
        model['outfits'] = [o for o in outfits(model.get('outfits', [])) if o['id'] != outfit_id]
        if model.get('accessories', {}).get('outfit') == outfit_id:
            model['accessories'] = {k: v for k, v in model['accessories'].items() if k != 'outfit'}
        self._save(document)
        if _outfit_id(outfit_id):
            (self.directory / model_id / 'outfits' / f'{outfit_id}.png').unlink(missing_ok=True)
        return model

    def model_path(self, model):
        filename = 'layered.json' if model['kind'] == 'layered' else 'model3.json'
        path = (self.directory / model['id'] / filename).resolve()
        if not path.is_relative_to(self.directory.resolve()):
            raise ValueError('Invalid installed model path.')
        return path

    def import_layered(self, profile, source, name='AI layered rig (experimental)'):
        from .layered import layered_bundle
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
