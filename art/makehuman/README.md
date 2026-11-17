# MakeHuman base data (CC0)

The realistic soldier's body and face start from the MakeHuman 1.x base mesh and data,
released by the MakeHuman team under CC0 1.0 (see LICENSE.md):

- `3dobjs/base.obj`: the base mesh (body, with helper geometry for eyes, eyelashes and more)
- `targets/macrodetails/...`: the macro targets for a young adult male of mixed ancestry,
  average to muscular build, a little taller than average (only the ones the soldier uses)
- `rigs/default.mhskel`, `rigs/default_weights.mhw`: the default skeleton and its skin weights
- `eyes/high-poly.obj`, `eyes/high-poly.mhclo`, `eyes/brown_eye.png`: the eye model, how it
  fits the face, and its texture

`art/blender/human.py` reads these to shape, pose and skin the body and build the head;
`art/blender/outfit.py` dresses it. Nothing here is loaded by the game itself: the game reads
what `art/blender/recoil_models.py` exports into `game/Assets/_Project/Resources/Models`.
