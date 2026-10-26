"""Read the ccx .dat, summarise, write the gmsh view."""
import math, re


def mises(s):
    sxx, syy, szz, sxy, sxz, syz = s
    return math.sqrt(0.5 * ((sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2)
                     + 3 * (sxy ** 2 + sxz ** 2 + syz ** 2))


def pct(vals, q):
    v = sorted(vals)
    return v[min(len(v) - 1, int(q * len(v)))]


def parse_dat(path):
    """Displacements of all nodes, von Mises per element (all integration points), reaction totals."""
    disp, per_ip, reactions = {}, {}, []
    cur = None
    lines = open(path).read().split("\n")
    for k, l in enumerate(lines):
        s = l.strip()
        if s.startswith("displacements"):
            cur = "U"
        elif s.startswith("stresses"):
            cur = "S"
        elif s.startswith("total force"):
            v = lines[k + 2].split() if not lines[k + 1].strip() else lines[k + 1].split()
            reactions.append(tuple(float(x) for x in v))
            cur = None
        elif cur and s:
            try:
                v = [float(x) for x in s.split()]
            except ValueError:
                cur = None
                continue
            if cur == "U" and len(v) == 4:
                disp[int(v[0])] = v[1:]
            elif cur == "S" and len(v) == 8:
                per_ip.setdefault(int(v[0]), []).append(mises(v[2:]))
    return disp, per_ip, reactions


def write_view(path, asm, regions, disp, per_ip):
    """Gmsh file: a physical group per part (and per support/load, as points), von Mises per element, displacement."""
    phys = {name: k for k, name in enumerate(asm.parts, start=1)}
    extra = {f"{r.kind}:{r.name}": len(phys) + k for k, r in enumerate(regions, start=1)}
    mean = {e: sum(v) / len(v) for e, v in per_ip.items()}
    used = sorted({n for _, t in asm.elem.values() for n in t[:4]})
    ids = {n: k for k, n in enumerate(used, start=1)}
    with open(path, "w") as f:
        f.write("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n$PhysicalNames\n%d\n" % (len(phys) + len(extra)))
        for name, k in list(phys.items()) + list(extra.items()):
            f.write('%d %d "%s"\n' % (3 if name in phys else 0, k, name))
        f.write("$EndPhysicalNames\n$Nodes\n%d\n" % len(used))
        for n in used:
            f.write("%d %.6f %.6f %.6f\n" % ((ids[n],) + asm.nodes[n]))
        points = [(r, n) for r in regions for n in r.nodes if n in ids]
        f.write("$EndNodes\n$Elements\n%d\n" % (len(asm.elem) + len(points)))
        for e, (nm, t) in asm.elem.items():
            f.write("%d 4 2 %d %d %s\n" % (e, phys[nm], phys[nm], " ".join(str(ids[n]) for n in t[:4])))
        for k, (r, n) in enumerate(points, start=len(asm.elem) + 1):
            f.write("%d 15 2 %d %d %d\n" % (k, extra[f"{r.kind}:{r.name}"], extra[f"{r.kind}:{r.name}"], ids[n]))
        f.write("$EndElements\n$ElementData\n1\n\"von Mises [MPa]\"\n1\n0.0\n3\n0\n1\n%d\n" % len(asm.elem))
        for e in asm.elem:
            f.write("%d %.4f\n" % (e, mean[e]))
        f.write("$EndElementData\n")
        ratio = [(e, mean[e] / asm.parts[nm].material.yield_) for e, (nm, _) in asm.elem.items()
                 if asm.parts[nm].material.yield_]
        if ratio:
            f.write("$ElementData\n1\n\"von Mises / yield\"\n1\n0.0\n3\n0\n1\n%d\n" % len(ratio))
            for e, r in ratio:
                f.write("%d %.5f\n" % (e, r))
            f.write("$EndElementData\n")
        f.write("$NodeData\n1\n\"displacement [mm]\"\n1\n0.0\n3\n0\n3\n%d\n" % len(used))
        for n in used:
            f.write("%d %.6f %.6f %.6f\n" % ((ids[n],) + tuple(disp[n])))
        f.write("$EndNodeData\n")
    # gmsh loads <file>.opt by itself: fixed ranges, so singular peaks do not turn everything blue
    hi = pct([m for v in per_ip.values() for m in v], .99)
    views = ["von Mises [MPa]"] + (["von Mises / yield"] if ratio else []) + ["displacement [mm]"]
    shown = 1 if ratio else 0
    with open(path + ".opt", "w") as f:
        for k, name in enumerate(views):
            f.write(f"View[{k}].Visible = {int(k == shown)};\n")
            if name.startswith("von Mises"):
                top = 1 if "yield" in name else hi
                f.write(f"View[{k}].RangeType = 2; View[{k}].CustomMin = 0; View[{k}].CustomMax = {top:g};\n"
                        f"View[{k}].SaturateValues = 1;\n")
