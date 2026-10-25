"""Triangle-mesh helpers: STL io, edge refinement, connected components, point queries."""
import heapq, math

# C3D10 faces S1..S4 as corner indices, and the midside nodes of each (CalculiX node order)
FACES = ((0, 1, 2), (0, 3, 1), (1, 3, 2), (2, 3, 0))
MIDS = ((4, 5, 6), (7, 8, 4), (8, 9, 5), (9, 7, 6))


def read_stl(path):
    tris, cur = [], []
    for l in open(path):
        a = l.split()
        if a and a[0] == "vertex":
            cur.append(tuple(float(x) for x in a[1:4]))
            if len(cur) == 3:
                tris.append(tuple(cur))
                cur = []
    return tris


def components(tris):
    parent = {}

    def find(v):
        while parent.setdefault(v, v) != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v

    key = lambda p: tuple(round(c, 5) for c in p)
    for t in tris:
        a, b, c = map(key, t)
        parent[find(b)] = find(a)
        parent[find(c)] = find(a)
    groups = {}
    for t in tris:
        groups.setdefault(find(key(t[0])), []).append(t)
    return list(groups.values())


def refine(tris, max_edge):
    """Bisect the longest edges until none is longer than max_edge.

    OpenSCAD triangulates big faces with holes into long slivers, which gmsh cannot
    parametrize; splitting the longest edge (conformally, both neighbours) evens them out."""
    key = lambda p: tuple(round(c, 5) for c in p)
    ids, verts, tri = {}, [], []
    for t in tris:
        row = []
        for p in t:
            k = key(p)
            if k not in ids:
                ids[k] = len(verts)
                verts.append(p)
            row.append(ids[k])
        tri.append(row)
    length = lambda a, b: math.dist(verts[a], verts[b])
    edges = {}
    for n, (a, b, c) in enumerate(tri):
        for e in ((a, b), (b, c), (c, a)):
            edges.setdefault(frozenset(e), set()).add(n)
    heap = [(-length(*sorted(e)), tuple(sorted(e))) for e in edges]
    heapq.heapify(heap)
    while heap and -heap[0][0] > max_edge:
        _, (a, b) = heapq.heappop(heap)
        if frozenset((a, b)) not in edges:
            continue
        m = len(verts)
        verts.append(tuple((verts[a][k] + verts[b][k]) / 2 for k in range(3)))
        for n in list(edges.pop(frozenset((a, b)))):
            i = tri[n].index(a) if (tri[n][(tri[n].index(a) + 1) % 3] == b) else tri[n].index(b)
            x, y, z = tri[n][i], tri[n][(i + 1) % 3], tri[n][(i + 2) % 3]      # edge x-y, apex z
            for e in ((y, z), (z, x)):
                edges[frozenset(e)].discard(n)
            tri[n] = [x, m, z]
            tri.append([m, y, z])
            new = len(tri) - 1
            edges[frozenset((y, z))].add(new)
            for e, owners in (((x, m), (n,)), ((m, z), (n, new)), ((z, x), (n,)), ((m, y), (new,))):
                edges.setdefault(frozenset(e), set()).update(owners)
                heapq.heappush(heap, (-length(*e), tuple(sorted(e))))
    return [tuple(verts[i] for i in t) for t in tri]


def bbox(tris):
    pts = [p for t in tris for p in t]
    return [(min(p[k] for p in pts), max(p[k] for p in pts)) for k in range(3)]



def point_triangle_dist(p, a, b, c):
    """Distance from p to triangle abc (Ericson, Real-Time Collision Detection)."""
    sub = lambda u, v: (u[0]-v[0], u[1]-v[1], u[2]-v[2])
    dot = lambda u, v: u[0]*v[0] + u[1]*v[1] + u[2]*v[2]
    ab, ac, ap = sub(b, a), sub(c, a), sub(p, a)
    d1, d2 = dot(ab, ap), dot(ac, ap)
    if d1 <= 0 and d2 <= 0:
        q = a
    else:
        bp = sub(p, b)
        d3, d4 = dot(ab, bp), dot(ac, bp)
        cp = sub(p, c)
        d5, d6 = dot(ab, cp), dot(ac, cp)
        vc, vb, va = d1*d4 - d3*d2, d5*d2 - d1*d6, d3*d6 - d5*d4
        if d3 >= 0 and d4 <= d3:
            q = b
        elif d6 >= 0 and d5 <= d6:
            q = c
        elif vc <= 0 and d1 >= 0 and d3 <= 0:
            v = d1 / (d1 - d3)
            q = tuple(a[k] + v*ab[k] for k in range(3))
        elif vb <= 0 and d2 >= 0 and d6 <= 0:
            w = d2 / (d2 - d6)
            q = tuple(a[k] + w*ac[k] for k in range(3))
        elif va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
            w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
            q = tuple(b[k] + w*(c[k] - b[k]) for k in range(3))
        else:
            denom = 1.0 / (va + vb + vc)
            v, w = vb * denom, vc * denom
            q = tuple(a[k] + ab[k]*v + ac[k]*w for k in range(3))
    return math.sqrt(sum((p[k] - q[k]) ** 2 for k in range(3)))


def near_surface(points, tris, tol, cell=4.0):
    """Ids of points within tol of any triangle (triangles hashed on a grid)."""
    grid = {}
    cellof = lambda v: int(math.floor(v / cell))
    for tri in tris:
        lo = [min(v[k] for v in tri) - tol for k in range(3)]
        hi = [max(v[k] for v in tri) + tol for k in range(3)]
        for i in range(cellof(lo[0]), cellof(hi[0]) + 1):
            for j in range(cellof(lo[1]), cellof(hi[1]) + 1):
                for k in range(cellof(lo[2]), cellof(hi[2]) + 1):
                    grid.setdefault((i, j, k), []).append(tri)
    return [nid for nid, p in points.items()
            if any(point_triangle_dist(p, *t) <= tol
                   for t in grid.get((cellof(p[0]), cellof(p[1]), cellof(p[2])), ()))]



def inside_mesh(p, tris):
    """Ray cast along a skewed direction (Moller-Trumbore); odd crossings = inside a closed mesh."""
    d = (1.0, 0.01237, 0.00713)
    hits = 0
    for a, b, c in tris:
        e1 = (b[0]-a[0], b[1]-a[1], b[2]-a[2])
        e2 = (c[0]-a[0], c[1]-a[1], c[2]-a[2])
        h = (d[1]*e2[2] - d[2]*e2[1], d[2]*e2[0] - d[0]*e2[2], d[0]*e2[1] - d[1]*e2[0])
        det = e1[0]*h[0] + e1[1]*h[1] + e1[2]*h[2]
        if abs(det) < 1e-12:
            continue
        s = (p[0]-a[0], p[1]-a[1], p[2]-a[2])
        u = (s[0]*h[0] + s[1]*h[1] + s[2]*h[2]) / det
        if u < 0 or u > 1:
            continue
        q = (s[1]*e1[2] - s[2]*e1[1], s[2]*e1[0] - s[0]*e1[2], s[0]*e1[1] - s[1]*e1[0])
        v = (d[0]*q[0] + d[1]*q[1] + d[2]*q[2]) / det
        if v < 0 or u + v > 1:
            continue
        if (e2[0]*q[0] + e2[1]*q[1] + e2[2]*q[2]) / det > 0:
            hits += 1
    return hits % 2 == 1


def triangle_area(a, b, c):
    u = (b[0]-a[0], b[1]-a[1], b[2]-a[2])
    v = (c[0]-a[0], c[1]-a[1], c[2]-a[2])
    return 0.5 * math.sqrt((u[1]*v[2]-u[2]*v[1])**2 + (u[2]*v[0]-u[0]*v[2])**2 + (u[0]*v[1]-u[1]*v[0])**2)


def write_stl(path, tris):
    with open(path, "w") as f:
        f.write("solid c\n")
        for t in tris:
            f.write("facet normal 0 0 0\nouter loop\n")
            for p in t:
                f.write("vertex %.6f %.6f %.6f\n" % p)
            f.write("endloop\nendfacet\n")
        f.write("endsolid c\n")
