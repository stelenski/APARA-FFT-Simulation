#!/usr/bin/env python3
"""
Radix-4 FFT mcode generator.

This script generates a complete mcode program for a N point radix-4 FFT for an input size N.
It uses a reference file (fft_new.mcode) that contains a complete program for N=64, followed by a library of blocks
that can be used for other sizes.  The generator selects, orders and repeats blocks and evaluates any N-dependent immediate values.
It does not change the instruction schedule.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REFERENCE = os.path.join(HERE, "fftN_new.mcode")

N_MIN = 16
N_MAX = 2048          # 3N 64-bit words must fit the simulator's 8192-word data memory
INT_RE = re.compile(r"(?<![\w$])-?\d+(?![\w])")


# ---------------------------------------------------------------------------
# reference parsing:  block -> list of bundles;  bundle = [label, [instr lines]]
# ---------------------------------------------------------------------------
def parse_reference(path):
    blocks, comments = {}, {}
    name = None
    with open(path) as f:
        for raw in f:
            st = raw.strip()
            m = re.match(r"//@BLOCK\s+(\w+)", st)
            if m:
                name = m.group(1)
                blocks[name], comments[name] = [], []
                continue
            if st.startswith("//@END"):
                name = None
                continue
            if name is None or not st:
                continue
            if st.startswith("//"):
                comments[name].append(st)
            elif re.match(r"^\w+:$", st):
                blocks[name].append([st[:-1], []])
            elif st in ("||", ";"):
                continue
            elif st != "$null":
                blocks[name][-1][1].append(st)
    return blocks, comments


def evaluate(instr, env):
    if "//@" not in instr:
        return instr
    code, expr = instr.split("//@", 1)
    val = eval(expr.strip(), {"__builtins__": {}}, dict(env))
    if code.strip().startswith("$set"):
        val = max(val, 0)                    # counter of a dropped (zero-trip) loop
        if val >= 65536:
            raise ValueError(f"constant out of range: {instr}")
    m = list(INT_RE.finditer(code))[-1]
    code = code[:m.start()] + str(val) + code[m.end():]
    return f"{code.rstrip():<50s}//@ {expr.strip()}"


def instantiate(bundles, env, suffix, labels):
    out = []
    for label, instrs in bundles:
        ins = []
        for i in instrs:
            i = evaluate(i, env)
            m = re.search(r"\$goto\s+(\w+)", i)
            if m and m.group(1) in labels:
                i = i[:m.start(1)] + m.group(1) + suffix + i[m.end(1):]
            ins.append(i)
        out.append([label + suffix if label in labels else label, ins])
    return out


# ---------------------------------------------------------------------------
# register-write analysis (used to merge a setup bundle into the previous one)
# ---------------------------------------------------------------------------
def writes(instr):
    code = instr.split("//")[0].strip()
    regs = [int(r) for r in re.findall(r"\$r(\d+)", code)]
    w = set()
    if code.startswith("$st") or code.startswith("$halt"):
        pass
    elif code.startswith("?"):
        w.add(regs[0])                       # branch counter is decremented
    elif code.startswith("$ld"):
        width = {"$u256": 4, "$u128": 2}.get(re.search(r"\((\$\w+)\)", code).group(1), 1)
        w.update(range(regs[0], regs[0] + width))
    elif regs:
        w.add(regs[0])
    m = re.search(r"\[\$r\d+\s*\+\s*\$r(\d+)\s*\+\+(\d+)\]", code)
    if m and int(m.group(2)):
        w.add(int(m.group(1)))               # post-incremented index register
    return w


def merge_setup_bundles(blocks):
    """If a block starts with a bundle of $set's only and the previous block ends with a
    straight-line bundle that has room and does not write those registers, move them there."""
    for prev, cur in zip(blocks, blocks[1:]):
        if not prev or len(cur) < 2:
            continue
        last, first = prev[-1][1], cur[0][1]
        if any("$goto" in i or "$halt" in i for i in last):
            continue
        if not first or not all(i.startswith("$set") for i in first):
            continue
        if len(last) + len(first) > 8:
            continue
        targets = set().union(*(writes(i) for i in first))
        if targets & set().union(set(), *(writes(i) for i in last)):
            continue
        last.extend(first)
        label = cur[0][0]
        del cur[0]
        cur[0][0] = label                    # keep the block's entry label


# ---------------------------------------------------------------------------
# FFT plan
# ---------------------------------------------------------------------------
def stage0_params(N):
    """Stage 0 (L=N) processes butterfly pairs (k,k+1), k even.
    W^{3k} comes from the half table: W[3k] if 3k < N/2, else conj(W[N-3k])."""
    T = 16 * N
    kst = next(k for k in range(N // 4 + 1) if 3 * k > N // 2)
    kinds = []
    for j in range(N // 8):
        k = 2 * j
        kinds.append("A" if k + 1 < kst else ("X" if k < kst else "B"))
    nA, nB, hasX = kinds.count("A"), kinds.count("B"), "X" in kinds
    kB = 2 * kinds.index("B")
    if hasX:
        kX = 2 * kinds.index("X")
        cout = T + 16 * (N - 3 * (kX + 1))   # conj W[N-3k] of element k+1 of the straddling pair
    else:
        cout = T + 16 * (N - 3 * kB)         # first pair of the conj region
    return dict(S0_LOOPA=nA if hasX else nA - 1, S0_NB=nB, S0_COUT=cout), hasX


def build_plan(N):
    """List of (block name, env, label suffix) and a readable stage list."""
    base = dict(N=N, T=16 * N)
    seq, desc = [], []

    def add(names, env, sfx=""):
        e = dict(base)
        e.update(env)
        for nm in names:
            seq.append((nm, e, sfx))

    if N == 16:
        L, tabL = 16, 16
    else:
        p, hasX = stage0_params(N)
        add(["s0_pro", "s0_A", "s0_TX" if hasX else "s0_TA", "s0_B"], p)
        desc.append(f"radix-4 L={N}")
        tabL = N // 4          # stage 0 leaves T1[m] = W_N^{4m} (m < N/8) in the twiddle area
        L = N // 4
        first = True
        while L >= 32:
            if first:
                add(["neg_pro", "neg_loop", "neg_fin"], dict(NEG_IT=N // 128))
                desc.append("twiddle table (negated part)")
                first = False
            elif tabL != L:
                add(["cmp_pro", "cmp_loop", "cmp_fin"], dict(CMP_IT=3 * L // 16), f"_L{L}")
                desc.append("twiddle table compaction")
            tabL = L
            add(["gen_pro", "gen_in", "gen_tr"], dict(Q=L // 4, G=N // L), f"_L{L}")
            desc.append(f"radix-4 L={L}")
            L //= 4
    if L == 16:
        add(["l16_pro", "l16_loop", "l16_fin"], dict(L16_IT=N // 16, S16=tabL // 16))
        add(["r4_pro", "r4_loop", "r4_fin"], dict(R4_IT=N // 16))
        desc += ["radix-4 L=16", "radix-4 L=4"]
    else:
        add(["l8_pro", "l8_loop", "l8_fin"], dict(L8_IT=N // 16, S8=tabL // 8))
        desc.append("radix-4 L=8 + radix-2 L=2 (fused)")
    return seq, desc


LOOP_TRIPS = {"s0_A": "S0_LOOPA", "s0_B": "S0_NB", "neg_loop": "NEG_IT-1", "cmp_loop": "CMP_IT-1",
              "l16_loop": "L16_IT-1", "l8_loop": "L8_IT-1", "r4_loop": "R4_IT-1"}


def generate(N, reference=REFERENCE):
    blocks, comments = parse_reference(reference)
    seq, desc = build_plan(N)
    groups = {}
    for name, env, sfx in seq:
        groups.setdefault(sfx, set()).update(lb for lb, _ in blocks[name])
    out = []
    for name, env, sfx in seq:
        if name in LOOP_TRIPS and eval(LOOP_TRIPS[name], {}, dict(env)) <= 0:
            continue                          # zero-trip loop: drop the block
        labels = groups[sfx] if sfx else set()
        out.append((name + sfx, instantiate(blocks[name], env, sfx, labels), comments[name]))
    merge_setup_bundles([b for _, b, _ in out])
    # the program must end with $halt (r4_fin / l8_fin carry it)
    if not any("$halt" in i for i in out[-1][1][-1][1]):
        out.append(("halt", [["halt", ["$halt"]]], []))
    defined = {lb for _, b, _ in out for lb, _ in b}
    for _, b, _ in out:
        for _, ins in b:
            for i in ins:
                m = re.search(r"\$goto\s+(\w+)", i)
                if m and m.group(1) not in defined:
                    raise RuntimeError(f"undefined branch target {m.group(1)}")
    text = [f"// Radix-4 FFT, N = {N}  (generated by generate_mcode.py from fftN_new.mcode)",
            "//   memory: x[n]=(re,im) at words 0..2N-1, twiddles W_N^k (k<N/2) at words 2N..3N-1",
            "//   output: X[k] in bit-reversed order, in place over x",
            "//   stages: " + " -> ".join(desc), ""]
    nb = 0
    for name, bundles, com in out:
        text.append(f"//@BLOCK {name}")
        text += com
        for label, ins in bundles:
            assert len(ins) <= 8, (label, ins)
            text += [f"{label}:", "  ||"] + ["  " + i for i in ins] + ["  $null"] * (8 - len(ins)) + [";"]
            nb += 1
        text.append("//@END")
    return "\n".join(text) + "\n", nb


def main():
    try:
        N = int(sys.argv[1] if len(sys.argv) > 1 else input("Enter FFT size N: "))
    except ValueError:
        sys.exit("N must be an integer")
    if N <= 0 or N & (N - 1):
        sys.exit("N must be a power of 2")
    if not (N_MIN <= N <= N_MAX):
        sys.exit(f"N must be between {N_MIN} and {N_MAX} "
                 f"(the FFT needs 3N 64-bit words; the simulator data memory has 8192)")
    text, nb = generate(N)
    out = f"fft_{N}.mcode"
    with open(os.path.join(HERE, out), "w") as f:
        f.write(text)
    print(f"Generated: {out}  ({nb} bundles of code; reference {os.path.basename(REFERENCE)} unchanged)")


if __name__ == "__main__":
    main()
