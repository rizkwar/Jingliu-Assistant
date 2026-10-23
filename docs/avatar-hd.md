# Sharper avatar rendering

**HD rendering** is enabled by default. Restart the assistant to use it; toggle
it in Settings and click **Save defaults** to keep the choice. The approved v5
portrait, rig, expression drawings, voice and personality are unchanged.

Inspection found a 1254×1254 source and correct Windows scaling. HD improves the
rendering path: it draws at 1.5× native display density, capped at ratio 3 and
2048 pixels per canvas edge, and samples full-resolution textures instead of
the original softer mipmap chain. Supersampling smooths fine outlines. Turning
HD off restores the original native-resolution/mipmap path to reduce graphics load.

At this machine's 125% scaling, the native renderer reported:

| Window size | Balanced canvas | HD canvas |
| --- | --- | --- |
| 320×350 logical pixels | 400×415 | 600×623 |
| 640×700 logical pixels | 800×853 | 1200×1279 |

The canvas excludes the resize-grip row. Both sizes were checked in the Windows
window and before/after screenshots inspected; HD has crisper eye and hair detail.
Evidence stays local in `.cache/avatar-balanced-*.png` and `.cache/avatar-hd-*.png`.
A hidden HD toggle was verified to draw zero frames.

This improves the existing source; it is not a new 4K portrait or restoration of
missing detail. Increase **Avatar size** if you want the face larger. HD requires
more graphics work and buffer memory. Stage 7's performance figures describe the
earlier balanced path. The newer [idle performance check](avatar-performance.md)
measures HD rendering and its reduced idle draw rate.

The local vendor changes are reproducible with `scripts/patch_avatar_runtime.py`,
which verifies the original pinned build hash before adding the sizing helper and
HD sampling. Vendor licenses remain intact. Review/reapply the patch when upgrading;
do not silently replace it with an unmodified runtime.

Suggested commit: `fix: improve avatar rendering sharpness`
