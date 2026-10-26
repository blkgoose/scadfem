"""scadfem model.scad [-D name=value ...] [--quick] [--mesh S] [--no-contact] [-o DIR] [--work DIR] [--open]"""
import argparse, math, os, re, shutil, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor

from . import fem, geom, materials, mesh, post, scad, tags

LOG = []


def say(msg=""):
    print(msg, flush=True)
    LOG.append(msg)


def unique(items):
    seen = {}
    for t in items:
        n = seen.get(t.name, 0) + 1
        seen[t.name] = n
        if n > 1:
            t.name = f"{t.name}{n}"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="scadfem", description=__doc__)
    ap.add_argument("scad")
    ap.add_argument("-D", dest="defines", action="append", default=[], metavar="NAME=VALUE",
                    help="passed to openscad (and recorded in the result folder name)")
    ap.add_argument("--quick", action="store_true", help="mesh twice as coarse, frictionless contacts left out")
    ap.add_argument("--mesh", type=float, default=1.0, metavar="S", help="scale every element size (0.5 = finer)")
    ap.add_argument("--no-contact", action="store_true", help="treat frictionless contacts as free")
    ap.add_argument("--parse-only", action="store_true", help="list the tags found and stop")
    ap.add_argument("-o", "--out", help="result folder (default <scad folder>/results/<name>)")
    ap.add_argument("--work", help="scratch folder (default: a temp dir)")
    ap.add_argument("--open", action="store_true", help="open the result in gmsh")
    a = ap.parse_args(argv)

    src = open(a.scad).read()
    try:
        all_tags = tags.parse(src)
    except tags.TagError as e:
        sys.exit(f"{a.scad}: {e}")
    parts = [t for t in all_tags if t.kind == "part"]
    regions = [t for t in all_tags if t.kind in ("fixed", "load")]
    unique(parts)
    unique(regions)
    mats = materials.table(all_tags)
    opts = {k: v for t in all_tags if t.kind == "options" for k, v in t.args.items()}
    modes = {}
    for t in all_tags:
        if t.kind == "contact":
            if len(t.words) != 2 or t.args.get("mode") not in ("tie", "frictionless", "free"):
                sys.exit(f"{a.scad}:{t.line}: contact needs two part names and mode=tie|frictionless|free")
            modes[frozenset(t.words)] = t.args["mode"]
    for t in parts:
        if str(t.args.get("material", "")).lower() not in mats:
            sys.exit(f"{a.scad}:{t.line}: part '{t.name}' needs material=<{'|'.join(mats)}>")
    for t in regions:
        if t.kind == "load" and "force" not in t.args:
            sys.exit(f"{a.scad}:{t.line}: load needs force=[fx,fy,fz]")
    if not parts:
        sys.exit(f"{a.scad}: no `//@sim material=...` part found")
    if not any(t.kind == "fixed" for t in regions):
        sys.exit(f"{a.scad}: no `//@sim fixed` support: the model would float")
    say(f"{a.scad}: {len(parts)} parts, {len(regions)} supports/loads")
    for t in parts:
        say(f"  part {t.name:12s} {t.args['material']}" + (f"  h={t.args['h']}" if "h" in t.args else ""))
    for t in regions:
        say(f"  {t.kind:5s} {t.name}" + (f"  force={t.args['force']}" if t.kind == "load" else ""))
    if a.parse_only:
        return

    suffix = "_".join(re.sub(r"[^\w.]+", "", d.replace("=", "")) for d in a.defines) + ("_quick" if a.quick else "")
    stem = os.path.splitext(os.path.basename(a.scad))[0]
    out_dir = a.out or os.path.join(os.path.dirname(os.path.abspath(a.scad)), "results", stem + (f"_{suffix}" if suffix else ""))
    work = a.work or tempfile.mkdtemp(prefix=f"scadfem_{stem}_")
    os.makedirs(work, exist_ok=True)
    tol = float(opts.get("tol", 0.2))
    scale = a.mesh * (2.0 if a.quick else 1.0)
    threads = str(os.cpu_count() or 1)

    say(f"workdir {work}")
    with ThreadPoolExecutor(max_workers=os.cpu_count()) as pool:
        stls = list(pool.map(lambda t: scad.export(a.scad, t, a.defines, work, f"t{t.line}"), parts + regions))
    surfaces = {id(t): geom.read_stl(p) for t, p in zip(parts + regions, stls)}

    allbox = geom.bbox([tri for t in parts for tri in surfaces[id(t)]])
    diag = math.dist([b[0] for b in allbox], [b[1] for b in allbox])
    base_h = float(opts.get("h", diag / 20))
    jobs = []
    for t in parts:
        for k, comp in enumerate(geom.components(surfaces[id(t)])):
            lo_hi = geom.bbox(comp)
            h = float(t.args.get("h", min(base_h, min(hi - lo for lo, hi in lo_hi) / 1.5))) * scale
            jobs.append((t, k, comp, h))
    def run_job(j):
        t, k, comp, h = j
        try:
            return mesh.mesh_component(comp, f"p{t.line}_{k}", work, h)
        except Exception as e:
            raise RuntimeError(f"{a.scad}:{t.line}: meshing part '{t.name}' (component {k}, "
                               f"{len(comp)} triangles, h={h:.3g}) failed: {type(e).__name__}: {e}\n"
                               f"  intermediate files are in {work}") from e

    try:
        with ThreadPoolExecutor(max_workers=os.cpu_count()) as pool:
            meshes = list(pool.map(run_job, jobs))
    except RuntimeError as e:
        sys.exit(str(e))
    asm = mesh.Assembly()
    for (t, k, comp, h), (nodes, tets, used_h) in zip(jobs, meshes):
        part = mesh.Part(t.name, mats[str(t.args["material"]).lower()])
        asm.add(part, nodes, tets, used_h)
        say(f"  {t.name}[{k}]: h={used_h:.2f} tets={len(tets)}")
    asm.finish()

    pairs = fem.find_pairs(asm, tol, modes, a.quick or a.no_contact)
    for p in pairs:
        extra = f", {len(p.slave_nodes)} nodes tied" if p.mode == "tie" else ""
        say(f"  {p.slave} touches {p.master}: {p.mode}{extra}")
        if p.mode == "tie" and not p.slave_nodes:
            say(f"  WARNING: no node of {p.slave} lies on {p.master} (tol={tol:g}): they are NOT connected."
                f" Refine with h=... on the part or --mesh 0.5, or raise tol in //@sim options")
    regs = [fem.make_region(asm, t, surfaces[id(t)], tol) for t in regions]
    for r in regs:
        say(f"  {r.kind} {r.name}: {len(r.nodes)} nodes")
    fem.write_inp(f"{work}/model.inp", asm, pairs, regs, tol, opts.get("contact_k"), a.quick)

    env = dict(os.environ, OMP_NUM_THREADS=threads, CCX_NPROC_EQUATION_SOLVER=threads)
    r = subprocess.run(["ccx", "model"], cwd=work, capture_output=True, text=True, env=env)
    if r.returncode != 0 or not os.path.exists(f"{work}/model.dat"):
        print(r.stdout[-2500:], r.stderr[-1500:])
        sys.exit("ccx failed (a model that can still move as a rigid body is the usual cause)")
    disp, per_ip, reactions = post.parse_dat(f"{work}/model.dat")

    say("")
    say("Results (MPa, von Mises; 99th pct ignores point singularities at loads and ties)")
    for p in asm.parts.values():
        v = [m for e in p.elems for m in per_ip.get(e, [])]
        y = p.material.yield_
        sf = f"   yield {y:g} -> safety {y / post.pct(v, .99):.2f} (p99) / {y / max(v):.2f} (max)" if y and max(v) > 0 else ""
        if max(v) == 0:
            sf = "   NO STRESS: the part carries no load (disconnected from the supports?)"
        say(f"  {p.name:12s} max {max(v):8.2f}   p99 {post.pct(v, .99):8.2f}   median {post.pct(v, .5):7.3f}{sf}")
    for pr in pairs:
        if pr.mode != "tie" or not pr.slave_nodes:
            continue
        s = asm.parts[pr.slave]
        tied = set(pr.slave_nodes)
        v = [m for e in s.elems if tied.intersection(asm.elem[e][1]) for m in per_ip.get(e, [])]
        y = f"   (yield {s.material.yield_:g})" if s.material.yield_ else ""
        say(f"  {pr.slave} at {pr.master}: max {max(v):8.2f}   p99 {post.pct(v, .99):8.2f}{y}")
    umax = max(disp.values(), key=lambda u: math.hypot(*u))
    say(f"  max displacement {math.hypot(*umax) * 1000:.1f} um")
    fixed = [r for r in regs if r.kind == "fixed"]
    for r, tot in zip(fixed, reactions[-len(fixed):]):      # one total per increment: keep the last
        say(f"  reaction of {r.name}: " + ", ".join(f"{x:.2f}" for x in tot) + " N")

    os.makedirs(out_dir, exist_ok=True)
    post.write_view(f"{out_dir}/result.msh", asm, regs, disp, per_ip)
    open(f"{out_dir}/summary.txt", "w").write("\n".join(LOG) + "\n")
    say(f"  view: gmsh {out_dir}/result.msh")
    if a.open:
        subprocess.Popen(["gmsh", f"{out_dir}/result.msh"])
