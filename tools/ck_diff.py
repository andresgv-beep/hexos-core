#!/usr/bin/env python3
"""
E2: comparador diferencial del CK.

La barrera exige TurnFrame idéntico campo por campo y ResponseContract
idéntico byte por byte. Esto lo comprueba sobre los volcados de ambas
implementaciones. Cualquier diferencia de orden o serialización es un fallo
hasta que alguien la explique — no se acepta "es equivalente".

    python3 tools/ck_diff.py informes/e2_ref_ck_policy.jsonl nuevo.jsonl
"""
import json, sys

CAMPOS = ["act", "artifact_active", "has_attachment", "trivial",
          "visible_budget", "thinking_budget", "contract_needed",
          "contract", "social_steer", "framed_user", "recall_context"]

def cargar(p):
    out = {}
    for n, l in enumerate(open(p, encoding="utf-8"), 1):
        l = l.strip()
        if not l: continue
        d = json.loads(l)
        if d["id"] in out:
            print(f"✗ id duplicado en {p}: {d['id']}"); sys.exit(1)
        out[d["id"]] = d
    return out

def main():
    a, b = cargar(sys.argv[1]), cargar(sys.argv[2])
    fallos = 0
    for cid in sorted(set(a) | set(b)):
        if cid not in a or cid not in b:
            print(f"✗ [{cid}] solo está en uno de los dos volcados"); fallos += 1; continue
        for c in CAMPOS:
            va, vb = a[cid].get(c), b[cid].get(c)
            if va == vb: continue
            fallos += 1
            if isinstance(va, str) and isinstance(vb, str):
                # Señalar el primer byte que difiere: "es equivalente" no vale.
                i = next((k for k in range(min(len(va), len(vb))) if va[k] != vb[k]),
                         min(len(va), len(vb)))
                print(f"✗ [{cid}] {c}: difiere en el byte {i}")
                print(f"    ref: …{va[max(0,i-30):i+30]!r}")
                print(f"    new: …{vb[max(0,i-30):i+30]!r}")
            else:
                print(f"✗ [{cid}] {c}: {va!r} → {vb!r}")
    print(f"\n{len(a)} casos · {fallos} diferencias")
    return 1 if fallos else 0

if __name__ == "__main__":
    sys.exit(main())
