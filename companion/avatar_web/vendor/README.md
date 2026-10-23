# Bundled mesh-avatar runtime

`mesh-avatar.js` is the browser build of `mesh-avatar` 0.2.1 from
[Mesh Avatar Studio](https://github.com/shinshin86/mesh-avatar-studio/tree/195ec284d3f7ae181782bf449069cb77e0650964/packages/runtime),
commit `195ec284d3f7ae181782bf449069cb77e0650964`.

Its MIT license is in `LICENSE`. The included fflate dependency's MIT notice is
preserved at the top of the bundle. No character artwork is included here.

To reproduce from that checkout, install its locked dependencies and run its
runtime build (`npm run build --workspace=mesh-avatar`); copy
`packages/runtime/dist/index.js` and `packages/runtime/LICENSE` here, then run
`python scripts/patch_avatar_runtime.py`. The patch verifies the pinned source
hash and adds bounded supersampling plus full-resolution texture sampling in HD
mode. Balanced mode retains the original mipmap filtering. The small sizing
helper is application-owned `render-quality.js`; no source artwork is modified.
Review and
verify upgrades separately rather than downloading runtime code at app startup.
