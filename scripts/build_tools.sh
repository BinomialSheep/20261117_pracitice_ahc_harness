#!/usr/bin/env bash
# Build the official Rust tools in problem/tools and install gen / vis / tester into problem/tools/bin/.
# The judge adapter (problem/tools/score_case.py) and every worker workspace use these binaries.
# Cargo's build directory is .build/tools-target, outside problem/tools, because problem/tools is
# copied into every round snapshot and every worker workspace.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tools="$root/problem/tools"
target="$root/.build/tools-target"

command -v cargo >/dev/null || { echo "cargo not found: install Rust from https://www.rust-lang.org/" >&2; exit 1; }

CARGO_TARGET_DIR="$target" cargo build --release --locked --bins --manifest-path "$tools/Cargo.toml"

mkdir -p "$tools/bin"
for name in gen vis tester; do
  install -m 755 "$target/release/$name" "$tools/bin/$name"
done

# Sanity check: the generator must reproduce the distributed input for seed 0.
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
(cd "$tmp" && printf '0\n' > seeds.txt && "$tools/bin/gen" seeds.txt --dir in)
cmp -s "$tmp/in/0000.txt" "$tools/in/0000.txt" || { echo "gen does not reproduce problem/tools/in/0000.txt" >&2; exit 1; }

echo "installed problem/tools/bin/{gen,vis,tester}; gen reproduces in/0000.txt"
