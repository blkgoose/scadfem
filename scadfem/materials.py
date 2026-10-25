"""Built-in materials (E and yield in MPa) and the `//@sim material name=... E=... nu=...` ones."""

BUILTIN = {                       # name: (E, nu, yield)
    "steel":      (200000.0, 0.30, 250.0),
    "stainless":  (193000.0, 0.30, 215.0),
    "aluminium":  (70000.0, 0.33, 240.0),
    "brass":      (100000.0, 0.34, 200.0),
    "titanium":   (110000.0, 0.34, 880.0),
    "pla":        (2000.0, 0.36, 20.0),      # lowest printed value, across the layers
    "petg":       (1800.0, 0.38, 25.0),
    "abs":        (2000.0, 0.35, 20.0),
    "wood":       (10000.0, 0.30, 30.0),
}


class Material:
    def __init__(self, name, E, nu, yield_=None):
        self.name, self.E, self.nu, self.yield_ = name, E, nu, yield_


def table(tags):
    mats = {n: Material(n, *v) for n, v in BUILTIN.items()}
    for t in tags:
        if t.kind == "material":
            n = str(t.args["name"]).lower()
            mats[n] = Material(n, t.args["E"], t.args.get("nu", 0.3), t.args.get("yield"))
    return mats
