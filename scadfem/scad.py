"""Render the tagged modules of an OpenSCAD file, one STL each."""
import functools, os, subprocess


@functools.cache
def backend_flags():
    """Newer OpenSCAD defaults to Manifold, whose STLs are full of zero-area and micro triangles gmsh chokes on."""
    try:
        h = subprocess.run(["openscad", "--help"], capture_output=True, text=True)
    except OSError:
        return []
    return ["--backend=CGAL"] if "--backend" in h.stdout + h.stderr else []


def export(scad_path, tag, defines, work, stem):
    """Render `tag.module()` alone into <work>/<stem>.stl.

    The generated file includes the original (so -D overrides reach its variables) and marks the call
    with OpenSCAD's `!` root modifier, which drops every other top-level statement of the original."""
    gen = f"{work}/{stem}.scad"
    open(gen, "w").write(f"include <{os.path.abspath(scad_path)}>\n!{tag.module}();\n")
    cmd = ["openscad"] + backend_flags() + [x for d in defines for x in ("-D", d)] + ["-o", f"{work}/{stem}.stl", gen]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(f"{work}/{stem}.stl"):
        raise RuntimeError(f"openscad failed on module '{tag.module}' (line {tag.line}):\n{r.stderr[-1500:]}")
    return f"{work}/{stem}.stl"
