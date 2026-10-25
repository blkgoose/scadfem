"""CalculiX model: ties and contacts between touching parts, supports, loads."""
from dataclasses import dataclass, field

from . import geom


@dataclass
class Pair:
    master: str
    slave: str
    mode: str                                        # tie | frictionless | free
    slave_nodes: list = field(default_factory=list)  # slave nodes within tol of the master skin
    contact_faces: tuple = ()                        # (slave faces, master faces) for frictionless


@dataclass
class Region:
    kind: str                                        # fixed | load
    name: str
    nodes: list
    dofs: str = "123"
    force: tuple = (0, 0, 0)
    weights: dict = field(default_factory=dict)      # node -> share of the force


def overlaps(a, b, tol):
    return all(a[k][0] - tol <= b[k][1] and b[k][0] - tol <= a[k][1] for k in range(3))


def find_pairs(asm, tol, modes, quick):
    """Every two parts whose surfaces touch (within tol). `modes` maps frozenset({a, b}) to a mode."""
    names = list(asm.parts)
    skins = {n: asm.skin(asm.parts[n]) for n in names}
    boxes = {n: asm.bbox(asm.parts[n].boundary) for n in names}
    pairs = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if not overlaps(boxes[a], boxes[b], tol):
                continue
            near = {a: set(geom.near_surface({n: asm.nodes[n] for n in asm.parts[a].boundary}, skins[b], tol)),
                    b: set(geom.near_surface({n: asm.nodes[n] for n in asm.parts[b].boundary}, skins[a], tol))}
            if not near[a] and not near[b]:
                continue
            mode = modes.get(frozenset((a, b)), "tie")
            if quick and mode == "frictionless":
                mode = "free"
            pa, pb = asm.parts[a], asm.parts[b]
            # stiffer part is the master; equal stiffness: the finer mesh
            key = lambda p: (-p.material.E, p.h)
            master, slave = sorted((pa, pb), key=key)
            pair = Pair(master.name, slave.name, mode)
            pair.slave_nodes = sorted(near[slave.name])
            if mode == "frictionless":
                pair.contact_faces = tuple(
                    [(e, f) for e, f in asm.parts[n].faces
                     if all(c in near[n] for c in (asm.elem[e][1][i] for i in geom.FACES[f]))]
                    for n in (slave.name, master.name))
            pairs.append(pair)
    return pairs


def select_nodes(asm, tris, tol):
    """Boundary nodes of the model inside, or within tol of, the closed mesh `tris`."""
    box = geom.bbox(tris)
    pts = {n: asm.nodes[n] for p in asm.parts.values() for n in p.boundary
           if all(box[k][0] - tol <= asm.nodes[n][k] <= box[k][1] + tol for k in range(3))}
    sel = set(geom.near_surface(pts, tris, tol))
    return sel | {n for n, p in pts.items() if n not in sel and geom.inside_mesh(p, tris)}


def make_region(asm, tag, tris, tol):
    sel = select_nodes(asm, tris, tol)
    faces = [(e, f) for p in asm.parts.values() for e, f in p.faces
             if all(asm.elem[e][1][i] in sel for i in geom.FACES[f])]
    if not sel:
        raise RuntimeError(f"'{tag.name}' (line {tag.line}) selects no node: it has to overlap the surface of a part")
    nodes = sorted(sel | {n for e, f in faces for n in asm.face_nodes(e, f)})
    reg = Region(tag.kind, tag.name, nodes, dofs=str(int(tag.args.get("dofs", 123))))
    if tag.kind == "load":
        reg.force = tuple(tag.args["force"])
        # consistent load of a quadratic tet face: all of it on the three midside nodes
        w = {}
        for e, f in faces:
            corners = [asm.nodes[asm.elem[e][1][i]] for i in geom.FACES[f]]
            area = geom.triangle_area(*corners)
            for i in geom.MIDS[f]:
                w[asm.elem[e][1][i]] = w.get(asm.elem[e][1][i], 0.0) + area / 3
        if not w:
            w = {n: 1.0 for n in nodes}
        total = sum(w.values())
        reg.weights = {n: v / total for n, v in w.items()}
    return reg


def write_inp(path, asm, pairs, regions, tol, contact_k, quick):
    out = ["*NODE, NSET=NALL"] + [f"{n}, {x:.6f}, {y:.6f}, {z:.6f}" for n, (x, y, z) in asm.nodes.items()]
    for p in asm.parts.values():
        out.append(f"*ELEMENT, TYPE=C3D10, ELSET={p.id}")
        out += [f"{e}, " + ", ".join(map(str, asm.elem[e][1])) for e in p.elems]
    for m in {p.material.name: p.material for p in asm.parts.values()}.values():
        out += [f"*MATERIAL, NAME={m.name.upper()}", "*ELASTIC", f"{m.E}, {m.nu}"]
    out += [f"*SOLID SECTION, ELSET={p.id}, MATERIAL={p.material.name.upper()}" for p in asm.parts.values()]

    skins = set()
    def skin(p):
        if p.id not in skins:
            skins.add(p.id)
            out.append(f"*SURFACE, NAME=SKIN_{p.id}, TYPE=ELEMENT")
            out.extend(f"{e}, S{f + 1}" for e, f in p.faces)
        return f"SKIN_{p.id}"

    slaved = set()
    for k, pr in enumerate(pairs, start=1):
        m, s = asm.parts[pr.master], asm.parts[pr.slave]
        if pr.mode == "tie":
            nodes = [n for n in pr.slave_nodes if n not in slaved]
            slaved.update(nodes)
            if nodes:
                out.append(f"*SURFACE, NAME=TS{k}, TYPE=NODE")
                out += [str(n) for n in nodes]
                out += [f"*TIE, NAME=TIE{k}, POSITION TOLERANCE={tol:g}, ADJUST=NO", f"TS{k}, {skin(m)}"]
        elif pr.mode == "frictionless":
            for tag, faces in zip("SM", pr.contact_faces):
                out.append(f"*SURFACE, NAME=C{tag}{k}, TYPE=ELEMENT")
                out += [f"{e}, S{f + 1}" for e, f in faces]
            out += [f"*SURFACE INTERACTION, NAME=INT{k}", "*SURFACE BEHAVIOR, PRESSURE-OVERCLOSURE=LINEAR",
                    f"{contact_k or 5 * s.material.E:g}",
                    f"*CONTACT PAIR, INTERACTION=INT{k}, TYPE=SURFACE TO SURFACE", f"CS{k}, CM{k}"]

    nonlinear = any(p.mode == "frictionless" for p in pairs)
    for r in regions:
        if r.kind == "fixed":
            out.append(f"*NSET, NSET=FIX_{r.name.upper()}")
            out += [str(n) for n in r.nodes]
    out += ["*BOUNDARY"]
    for r in regions:
        if r.kind == "fixed":
            out += [f"FIX_{r.name.upper()}, {d}" for d in r.dofs]
    out += ["*STEP, INC=200", "*STATIC",
            "0.1, 1.0, 1e-4, 0.25" if nonlinear else "1.0, 1.0", "*CLOAD"]
    for r in regions:
        if r.kind == "load":
            for n, w in r.weights.items():
                out += [f"{n}, {d}, {r.force[d - 1] * w:.8g}" for d in (1, 2, 3) if r.force[d - 1]]
    for r in regions:
        if r.kind == "fixed":
            out += [f"*NODE PRINT, NSET=FIX_{r.name.upper()}, TOTALS=ONLY", "RF"]
    out.append("*NODE PRINT, NSET=NALL")
    out.append("U")
    out += [x for p in asm.parts.values() for x in (f"*EL PRINT, ELSET={p.id}, FREQUENCY=1", "S")]
    out.append("*END STEP")
    open(path, "w").write("\n".join(out) + "\n")
