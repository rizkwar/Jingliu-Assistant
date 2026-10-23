# Bundled mesh-avatar runtime

`mesh-avatar.js` is the unmodified browser build of `mesh-avatar` 0.2.1 from
[Mesh Avatar Studio](https://github.com/shinshin86/mesh-avatar-studio/tree/195ec284d3f7ae181782bf449069cb77e0650964/packages/runtime),
commit `195ec284d3f7ae181782bf449069cb77e0650964`.

Its MIT license is in `LICENSE`. The included fflate dependency's MIT notice is
preserved at the top of the bundle. No character artwork is included here.

To reproduce from that checkout, install its locked dependencies and run its
runtime build (`npm run build --workspace=mesh-avatar`); copy
`packages/runtime/dist/index.js` and `packages/runtime/LICENSE` here. Review and
verify upgrades separately rather than downloading runtime code at app startup.
