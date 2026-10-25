"""Render the tagged modules of an OpenSCAD file, one STL each."""
import os, subprocess


def export(scad_path, tag, defines, work, stem):
    """Render `tag.module()` alone into <work>/<stem>.stl.

    The generated file includes the original (so -D overrides reach its variables) and marks the call
    with OpenSCAD's `!` root modifier, which drops every other top-level statement of the original."""
    gen = f"{work}/{stem}.scad"
    open(gen, "w").write(f"include <{os.path.abspath(scad_path)}>\n!{tag.module}();\n")
    cmd = ["openscad"] + [x for d in defines for x in ("-D", d)] + ["-o", f"{work}/{stem}.stl", gen]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(f"{work}/{stem}.stl"):
        raise RuntimeError(f"openscad failed on module '{tag.module}' (line {tag.line}):\n{r.stderr[-1500:]}")
    return f"{work}/{stem}.stl"
