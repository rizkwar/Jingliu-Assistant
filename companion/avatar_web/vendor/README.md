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
mode. Balanced mode retains the original mipmap filtering. It also adds the
optional `advanceStable(seconds)` API: motion and hair springs advance in steps
of at most 20 ms, then the mesh deforms and draws once. A stalled frame advances
at most 100 ms; sprite fades receive that whole elapsed frame once. The original
`advance(seconds, fps)` and automatic rendering APIs retain their behavior.

The small helpers are application-owned `render-quality.js` and `stable-step.js`,
served alongside the module by the local asset service; no source artwork is
modified. The patch is idempotent and accepts only these known LF-normalized
bundles:

- Original pinned build: `691301e4a2a89779617de4f4bf6c407c3003dc27161f5e4a3665566dfcff8e87`
- Previous HD-only build: `188ffa03914eb5ed765d98b7aa3cd273bdc5760cc0755ed92dab2ec42e096326`
- Current HD + stable-frame build: `1576e6550bcc64860cd4d06921f9a9df067e553bb4bd6301e6a32ffc45086b7e`

Review and verify upgrades separately rather than downloading runtime code at app
startup. The original MIT notices remain in the bundle and `LICENSE`.
