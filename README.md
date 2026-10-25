# scadfem

Static FEM of an OpenSCAD model, driven by comments in the `.scad` file.
OpenSCAD → one STL per tagged block → gmsh tet meshes → CalculiX → a gmsh file with the result.
Units are mm / N / MPa; only the Python standard library is used. The built file needs python3, gmsh,
ccx (CalculiX) and openscad on the PATH of whoever runs it.

    nix build && ./result/bin/scadfem examples/cantilever.scad   # the bashball: one file to distribute
    ./main.sh examples/cantilever.scad                          # from the checkout, inside the direnv/flake shell
    scadfem model.scad -D rod_length=100 --quick --open

Results go to `<scad folder>/results/<name>[_<defines>][_quick]/` (`result.msh`, `summary.txt`);
`result.msh` has a physical group per part (toggle them in gmsh), von Mises per element,
the displacement, and the supports/loads as point groups so you can check where they landed.

## Tags

`part`, `fixed` and `load` tag the `module name(...)` definition that follows; the tool renders `name();` alone
(a generated file `include`s yours and marks the call with `!`), so the module is placed exactly as written.

| tag | meaning |
|---|---|
| `//@sim material=steel [name=rod] [h=2]` | the module is a solid part (`name` defaults to the module name); `h` is the element size (default: the thinner of the model diagonal/20 and thickness/1.5) |
| `//@sim fixed [name=..] [dofs=123]` | boundary nodes of the model inside the module's solid are clamped |
| `//@sim load force=[fx,fy,fz] [name=..]` | total force (N), spread over the boundary faces inside the solid (consistent for quadratic tets) |
| `//@sim material name=maple E=10000 nu=0.3 yield=40` | defines a material (no module) |
| `//@sim contact a b mode=tie\|frictionless\|free` | how two touching parts interact (no module) |
| `//@sim options h=6 tol=0.2 contact_k=1e4` | global element size, touch tolerance (mm), contact stiffness |

Built-in materials: steel, stainless, aluminium, brass, titanium, pla, petg, abs, wood (see `materials.py`).

## Rules worth knowing

- Name the tagged modules so they cannot clash with modules of the files you include (e.g. `fem_body`);
  the file's own top-level geometry is ignored, so it can keep its preview. `-D` reaches every included file.
- Parts are meshed separately. Parts that touch (surfaces within `tol`) are **tied** (perfect bond) by
  default: the stiffer part is the master, the softer part's nodes are the slaves. Cut slots in the
  softer part (`difference()`) rather than overlapping the solids. `frictionless` is a no-tension contact
  pair and makes the run nonlinear (slower); `--quick` and `--no-contact` turn it into `free`.
- `fixed`/`load` regions are plain geometry that select nodes on the surface of the parts; make them
  overlap that surface (a thin slab straddling the face works). Keep them away from other parts' faces.
- The summary gives von Mises max / 99th percentile / median per part and the safety factor against the
  material's yield, the stress in the softer part around each tie (to judge a glue/PLA bond), and the
  reaction of every support (it must equal the applied load).
- The 99th percentile ignores point singularities at loads and ties; the max includes them.
- `--mesh 0.5` halves every element size; `--quick` doubles them.

## Examples

- `examples/cantilever.scad`: checked against beam theory (0.796 mm vs 0.80, 119 vs 120 MPa at `--mesh 0.4`).
- `examples/butt_joint.scad`: two PLA blocks, steel bar, frictionless butt.
  `simulation/stl_joint.py` (rod 99th pct 110 MPa at 550 N).

Tests: `PYTHONPATH=. python3 -m unittest discover -s tests` (in the flake shell, `direnv allow` once).
