#!/usr/bin/env bash
# Entry point of the bashball (`nix build` makes ./result/bin/scadfem). Straight from the checkout,
# ./main.sh does the same, using scadfem/ next to it.
for tool in python3 gmsh ccx openscad; do
    command -v "$tool" >/dev/null || { echo "scadfem: $tool is not installed" >&2; exit 1; }
done

src="${_tmpdir:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
PYTHONPATH="$src" PYTHONDONTWRITEBYTECODE=1 exec python3 -m scadfem "$@"
