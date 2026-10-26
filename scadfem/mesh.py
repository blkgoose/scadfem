"""Tet meshes with gmsh, merged into one numbered model."""
import subprocess
from dataclasses import dataclass, field

from . import geom


def read_msh(path):
    """Nodes and 10-node tets (CalculiX node order) of a gmsh 2.2 file."""
    nodes, tets = {}, []
    lines = open(path).read().split("\n")
    i = 0
    while i < len(lines):
        if lines[i] == "$Nodes":
            cnt = int(lines[i + 1])
            for l in lines[i + 2:i + 2 + cnt]:
                a = l.split()
                nodes[int(a[0])] = (float(a[1]), float(a[2]), float(a[3]))
            i += cnt + 2
        elif lines[i] == "$Elements":
            cnt = int(lines[i + 1])
            for l in lines[i + 2:i + 2 + cnt]:
                a = l.split()
                if int(a[1]) == 11:
                    ns = [int(x) for x in a[3 + int(a[2]):]]
                    ns[8], ns[9] = ns[9], ns[8]            # gmsh -> abaqus midside order
                    tets.append(ns)
            i += cnt + 2
        i += 1
    return nodes, tets


GMSH_TIMEOUT = 60


def flat_tets(nodes, tets, h):
    """Count tets whose volume is ~0 or negative: CalculiX stops on a nonpositive jacobian."""
    bad = 0
    for t in tets:
        a, b, c, d = (nodes[i] for i in t[:4])
        u, v, w = ([q[k] - a[k] for k in range(3)] for q in (b, c, d))
        det = u[0]*(v[1]*w[2] - v[2]*w[1]) - u[1]*(v[0]*w[2] - v[2]*w[0]) + u[2]*(v[0]*w[1] - v[1]*w[0])
        if det / 6 <= 1e-7 * h ** 3:
            bad += 1
    return bad


def mesh_component(tris, name, work, h):
    """Mesh one closed triangle surface. Returns nodes, tets and the size actually used."""
    r = None
    for _ in range(3):
        for edge in (2, 1.5, 1, 3):           # gmsh fails now and then for one particular surface mesh
            # openscad's sliver triangles make gmsh fail unless the long edges are bisected first
            geom.write_stl(f"{work}/{name}.stl", geom.refine(tris, edge * h))
            # reparametrizing the surface can loop forever on some shapes: bound it, then keep the triangles as they are
            for reparam in (1, 0):
                with open(f"{work}/{name}.geo", "w") as f:
                    f.write(f'Merge "{name}.stl";\nMesh.MeshSizeMax = {h}; Mesh.MeshSizeMin = {h / 3};\n'
                            f"ClassifySurfaces{{ 40*Pi/180, 1, {reparam}, 40*Pi/180 }};\nCreateGeometry;\n"
                            "Surface Loop(1) = Surface{:};\nVolume(1) = {1};\n"
                            "Mesh.ElementOrder = 2; Mesh.SecondOrderLinear = 1; Mesh.Algorithm3D = 1;\n"
                            "Mesh.MshFileVersion = 2.2;\n" + ("" if reparam else "Mesh.OptimizeNetgen = 1;\n"))
                try:
                    r = subprocess.run(["gmsh", "-3", "-nopopup", f"{name}.geo", "-o", f"{name}.msh"], cwd=work,
                                       capture_output=True, text=True, timeout=GMSH_TIMEOUT)
                except subprocess.TimeoutExpired:
                    print(f"  {name}: gmsh timed out after {GMSH_TIMEOUT}s (edge {edge}h, reparametrize={reparam}), retrying",
                          flush=True)
                    continue
                if r.returncode == 0:
                    nodes, tets = read_msh(f"{work}/{name}.msh")
                    flat = flat_tets(nodes, tets, h)
                    if not flat:
                        return nodes, tets, h
                    print(f"  {name}: gmsh made {flat} flat/inverted tets (edge {edge}h, reparametrize={reparam}), retrying",
                          flush=True)
        h *= 0.93
    raise RuntimeError(f"gmsh could not mesh {name} (last attempt: "
                       f"{'timed out' if r is None else 'failed'}):\n{'' if r is None else (r.stdout + r.stderr)[-800:]}")


@dataclass
class Part:
    name: str
    material: object
    h: float = 0.0
    elems: list = field(default_factory=list)       # global element ids
    faces: list = field(default_factory=list)       # boundary faces (element id, face index 0..3)
    nodes: set = field(default_factory=set)         # every node of the part
    boundary: set = field(default_factory=set)      # nodes on the boundary faces, midsides included

    @property
    def id(self):
        return "".join(c if c.isalnum() else "_" for c in self.name).upper()


class Assembly:
    def __init__(self):
        self.nodes = {}
        self.elem = {}                               # element id -> (part name, node list)
        self.parts = {}
        self._shift = 0

    def add(self, part, nodes, tets, h):
        p = self.parts.setdefault(part.name, part)
        p.h = max(p.h, h)
        for i, xyz in nodes.items():
            self.nodes[i + self._shift] = xyz
        for t in tets:
            e = len(self.elem) + 1
            t = [i + self._shift for i in t]
            self.elem[e] = (part.name, t)
            p.elems.append(e)
            p.nodes.update(t)
        self._shift = max(self.nodes) + 1

    def finish(self):
        for p in self.parts.values():
            count = {}
            for e in p.elems:
                t = self.elem[e][1]
                for f, idx in enumerate(geom.FACES):
                    count.setdefault(frozenset(t[i] for i in idx), []).append((e, f))
            p.faces = [ef[0] for ef in count.values() if len(ef) == 1]
            p.boundary = {n for e, f in p.faces for n in self.face_nodes(e, f)}
        used = {n for p in self.parts.values() for n in p.nodes}
        self.nodes = {i: xyz for i, xyz in self.nodes.items() if i in used}

    def face_nodes(self, e, f):
        t = self.elem[e][1]
        return [t[i] for i in geom.FACES[f] + geom.MIDS[f]]

    def skin(self, part):
        """Corner triangles of a part's boundary, as coordinates."""
        return [tuple(self.nodes[self.elem[e][1][i]] for i in geom.FACES[f]) for e, f in part.faces]

    def bbox(self, nodeset):
        pts = [self.nodes[n] for n in nodeset]
        return [(min(p[k] for p in pts), max(p[k] for p in pts)) for k in range(3)]
