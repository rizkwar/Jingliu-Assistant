import unittest

from companion.avatar.presets import AVATAR_MOTION_PRESETS, motion_preset_name
from companion.core.config import DEFAULT_MODEL, Settings


class AvatarPresetTests(unittest.TestCase):
    def test_natural_preserves_existing_defaults_and_every_preset_fits_controls(self):
        settings = Settings('', DEFAULT_MODEL, 'Test character', 'Test personality')
        self.assertEqual(AVATAR_MOTION_PRESETS['Natural'],
                         (settings.avatar_motion, settings.avatar_gaze, settings.avatar_hair))
        for motion, gaze, hair in AVATAR_MOTION_PRESETS.values():
            self.assertTrue(0 <= motion <= 100)
            self.assertTrue(0 <= gaze <= 100)
            self.assertTrue(20 <= hair <= 80)
        self.assertEqual(AVATAR_MOTION_PRESETS['Lively'][:2], AVATAR_MOTION_PRESETS['Natural'][:2])
        self.assertGreater(AVATAR_MOTION_PRESETS['Lively'][2], AVATAR_MOTION_PRESETS['Natural'][2])

    def test_names_are_derived_from_all_three_exact_values(self):
        for name, values in AVATAR_MOTION_PRESETS.items():
            self.assertEqual(motion_preset_name(*values), name)
            for index in range(3):
                custom = list(values)
                custom[index] -= 1
                self.assertEqual(motion_preset_name(*custom), 'Custom')


if __name__ == '__main__':
    unittest.main()
