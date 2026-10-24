# AI v5 layered rig experiment

The approved AI portrait has a separate **AI v5 layered rig (experimental)**
option in Settings. The original AI portrait and the downloaded Live2D model
remain available. Installing the experiment does not change the selected model.

## Try it

1. Quit the assistant from its tray menu and open **Start Mira.cmd** again.
2. Open **Settings > Jingliu visual model** and choose
   **AI v5 layered rig (experimental)**.
3. Enable the desktop avatar and animation. Start with the **Natural** preset.
4. Press **Preview movement** to see left/right turns, looking up/down, a tilt
   and a return to rest. The preview is silent.
5. Try a spoken reply and Stop. Existing cursor glances and conversation states
   also use this rig. Choose **AI portrait (current)** to compare or return.

The voice, character instructions, conversation and memories belong to the
character and do not change with this selector. No new inference service or
runtime download is needed for this renderer.

## What was built

The optional renderer uses eleven independently drawn surfaces:

- A completed rear-hair backing, left and right rear hair.
- The torso, neck, and face/jaw.
- The earring, crown, left and right front locks, and fringe.

The original v5 pixels supply the visible cutouts. Two generated paintings
complete the hidden head/neck/costume and rear hair. They are used behind the
cutouts, rather than replacing the approved face with a new portrait. The
existing physics weight mask is refined using color at the face boundary before
it is used to separate the parts. Underpainting fills newly exposed areas.

The face is projected on a curved depth surface with a separate nose region.
Yaw changes relative eye/nose/cheek spacing; pitch changes the chin position.
The neck blends toward an anchored collar, and the torso follows the existing
slower body motion. This is an experimental **2.5D mesh rig**, not an editable
Cubism project, full 3D reconstruction, or a professionally authored Live2D rig.
It does not reuse or modify the downloaded creator's rig or textures.

The full app control range maps to about 20.4 degrees of yaw, 10.8 degrees of
pitch and 8 degrees of roll in the projection. Ordinary idle uses smaller
movements. These are mathematical rotation limits, not a measured likeness to
the reference video or a guarantee that every angle looks equally good.

Hair roots remain attached while damped springs add restrained tip motion.
Springs use an exact damped solution with bounded steps; redraws do not inject
velocity. The earring has its own response. Blinking, iris movement, breathing,
thinking eyes and amplitude lip-sync use the existing conversation/playback
bridge. Stop clears mouth movement immediately; hidden avatars stop drawing.

## Art and reproducibility

All artwork and generated previews remain in ignored local storage:

| Local path | Purpose |
| --- | --- |
| `.cache/mesh-avatar-studio/projects/jingliu/` | Original approved v5 image, calibrated mask and facial drawings |
| `.cache/avatar-rigs/jingliu-layered/underpaint.png` | Generated hidden head/neck/costume painting |
| `.cache/avatar-rigs/jingliu-layered/back-hair.png` | Generated completed rear hair |
| `.cache/avatar-rigs/jingliu-layered/prompts.json` | Exact prompts and tool used for those two edits |
| `data/avatar_models/layered-*/` | Installed version: manifest and explicit PNG resources |
| `.cache/layered-avatar-qa/` | Avatar-only captures, silent preview and check results |

The two paintings were edited from the original v5 image using the built-in
image generation tool, with transparency requested, then visually inspected.
They are hidden repair assets, not replacement character designs. The exact
prompt set is saved with them. No API key is needed to run the installed rig.
Character rights are separate from the assistant code's license.

To rebuild after restoring those local assets:

```powershell
.\.venv\Scripts\python.exe scripts/build_layered_jingliu.py
```

The builder copies only required artwork and numeric rig metadata, installs a
content-addressed local model, and leaves the selected option unchanged. A new
art version gets a new model ID. It does not alter the original source image or
the original `.mavatar`. Runtime cutout/compositing code lives in
`companion/avatar_web/layered-avatar.js`; projection and springs live in
`layered-rig.js`. This first version is calibrated specifically to the square
1254-pixel v5 image; it is not an automatic rigger for arbitrary portraits.

## Verification and limits

The native check runs the production renderer with temporary preferences,
in-memory conversations and fake microphone/speech controllers:

```powershell
.\.venv\Scripts\python.exe scripts/check_layered_avatar.py
node --test tests/*.test.mjs
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

It captures both turn directions, up/down and a diagonal; checks finite layer
state, silent-preview mouth closure, synthetic playback/Stop, hiding, pause,
resize, repeated model switching, reload and shutdown. Its recordings contain
only the avatar canvas. It makes no microphone, speech-generation or response
provider calls. A synthetic playback envelope checks the mouth bridge, not the
perceived synchronization of a real voice reply.

Six geometry/physics regressions cover neutral coordinates, changing facial
perspective, moving chin/anchored collar, shared hair roots, sampled triangle
winding at combined limits, jitter recovery and equivalent spring timing at
30/60/120 Hz. Passing them does not certify every visible texture boundary.

The full suites passed **288 Python tests** and **69 JavaScript tests**. The
native lifecycle check passed; subsequent art-only checks refreshed the five
pose captures, playback/Stop check and `layered-preview.mp4` after edge repairs.
The local `verification.json` records lifecycle results, and
`art-verification.json` records the last pose revision.

The rendered poses were inspected and the first obvious open hair cuts,
double collar and a leftover chin outline on the neck were repaired. Fine hair and earring edges remain less clean
than a manually prepared model, especially during larger combined turns. The
underpainting and approximate depth cannot produce a fully authored profile
view. Half-eye drawings still include their irises. Resource use has not been
benchmarked; the existing draw cadence remains a target, not a measured FPS claim.

The next art-quality step is to refine the individual part mattes and draw
overlap/occluded areas for authored left/right/up/down keyforms. That work can
build toward a Cubism rig without replacing the current options. The
[Live2D material separation guide](https://docs.live2d.com/en/cubism-editor-manual/divide-the-material/)
and [deformer documentation](https://docs.live2d.com/en/cubism-editor-manual/deformer/)
describe the part/deformer approach that informs this experiment.

Suggested commit: `feat: add experimental layered depth rig for AI Jingliu`
