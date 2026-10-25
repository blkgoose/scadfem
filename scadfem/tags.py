"""Parse the `//@sim` annotations of an OpenSCAD file.

    //@sim material=steel name=rod h=2      the module below is a solid part
    //@sim fixed                             nodes of the model inside the module's solid are clamped
    //@sim load force=[0,550,0]              ... carry this total force (N)
    //@sim material name=maple E=10000 nu=0.3 yield=40     define a material (no module)
    //@sim contact body holder mode=frictionless           how two touching parts interact
    //@sim options h=6 tol=0.2                              global settings

part, fixed and load tag the `module name() { ... }` that follows; the tool renders `name();` alone.
The first bare word is the kind (`part` when missing). Values are plain words or [a,b,c] lists.
"""
import re
from dataclasses import dataclass

KINDS = ("part", "fixed", "load", "material", "contact", "options")
NEEDS_MODULE = ("part", "fixed", "load")
LINE = re.compile(r"^[ \t]*//@sim\b(.*)$", re.M)
WORD = re.compile(r"(\w+)=(\[[^\]]*\]|\S+)|(\S+)")
MODULE = re.compile(r"module\s+(\w+)\s*\(")


class TagError(Exception):
    pass


@dataclass
class Tag:
    kind: str
    args: dict
    words: list
    line: int
    module: str = ""
    name: str = ""


def parse_value(v):
    if v.startswith("["):
        return [float(x) for x in v[1:-1].split(",")]
    try:
        return float(v)
    except ValueError:
        return v


def skip_blank(src, i):
    """Skip whitespace and comments."""
    while i < len(src):
        if src[i].isspace():
            i += 1
        elif src.startswith("//", i):
            i = src.find("\n", i)
            i = len(src) if i < 0 else i
        elif src.startswith("/*", i):
            i = src.find("*/", i)
            i = len(src) if i < 0 else i + 2
        else:
            break
    return i


def parse(src):
    """All tags of a source text."""
    tags = []
    for m in LINE.finditer(src):
        line = src.count("\n", 0, m.start()) + 1
        args, words = {}, []
        for k, v, w in WORD.findall(m.group(1)):
            if w:
                words.append(w)
            else:
                args[k] = parse_value(v)
        kind = words.pop(0) if words and words[0] in KINDS else "part"
        tag = Tag(kind, args, words, line)
        if kind in NEEDS_MODULE:
            start = skip_blank(src, m.end())
            if LINE.search(src, m.end(), start):
                raise TagError(f"line {line}: two //@sim tags in a row, put a module after each")
            mod = MODULE.match(src, start)
            if not mod:
                raise TagError(f"line {line}: `{kind}` has to be followed by a `module name(...)` definition")
            tag.module = mod.group(1)
            tag.name = str(args.get("name") or (mod.group(1) if kind == "part" else kind))
        tags.append(tag)
    return tags
