"""Named combinations of the avatar's existing movement controls."""

from types import MappingProxyType


# Keep Natural identical to the existing defaults. Lively adds hair follow-through
# within the same reviewed head/gaze bounds, rather than increasing those bounds.
AVATAR_MOTION_PRESETS = MappingProxyType({
    "Calm": (45, 55, 30),
    "Natural": (100, 100, 45),
    "Lively": (100, 100, 65),
})


def motion_preset_name(motion, gaze, hair):
    """Derive the name from slider values; no second saved preset value exists."""
    values = (motion, gaze, hair)
    return next((name for name, preset in AVATAR_MOTION_PRESETS.items()
                 if preset == values), "Custom")
