#!/usr/bin/env python3
"""Reproduce the line counts of Table 1 ("What one job costs").

Usage:
    scripts/count_loc.py --mlir <path/to/llvm-project> --mimir <path/to/mimir>
    scripts/count_loc.py --mlir ... --mimir ... --check     # exit 1 on mismatch
    scripts/count_loc.py --mlir ... --mimir ... --verbose   # per-file breakdown

Counting rule, applied identically to both frameworks: a line counts if it is
non-blank and is not a comment.  Block comments are removed first; a line whose
first non-space characters are //, /// or # does not count.  Nothing else is
filtered -- no attempt is made to discount braces, includes or boilerplate.

Every line of the two .mim plugin sources is attributed to exactly one row:
    tensor.mim   = "define" + "tiling"          (schedule library -> tiling)
    btensor.mim  = "define" + "tiling"          (nest algebra     -> tiling)
so the rows partition the sources rather than sampling them.

Reference revisions (the ones reported in the paper):
    MLIR   llvm-project  904b9515757ab8b3d22095d455a044c4b33dc447   (2026-08-05)
    MimIR  mimir         21b15a3aa3                                 (2026-09-09)
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

MLIR_REV = "904b9515757ab8b3d22095d455a044c4b33dc447"
MIMIR_REV = "21b15a3aa3"

# Table 1, plus the figures quoted in its footnote and in the surrounding text.
EXPECTED = {
    "define.mlir": 8606,      "define.mimir": 431,
    "define.mlir.per_op": 106, "define.mimir.per_op": 13,
    "matched.ops.mlir": 13,   "matched.ops.mimir": 18,
    "matched.mlir": 1178,     "matched.mimir": 300,
    "matched.mlir.per_op": 91, "matched.mimir.per_op": 17,
    "covered.ops": 41,        "covered.mlir": 2835,
    "fold.mlir": 659,         "fold.mimir": 263,
    "lower.mlir": 763,        "lower.mimir": 519,
    "affine.mlir": 3155,      "affine.mimir": 26,
    "tiling.mlir": 3900,      "tiling.mimir": 403,
    "linalg.named_ops": 81,   "tensor.operations": 33,
    "tensor.annexes": 42,     "tensor.defined_in_mim": 16,
    "excluded.direct_lowering": 431,
    "total.mimir_cpp": 2594,
}

# ---------------------------------------------------------------- line counting

BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
# NB: a leading `*` is NOT treated as a comment.  Block comments are removed
# wholesale above, so the lines that survive and start with `*` are code --
# pointer dereferences and wrapped expressions (`*hasPoison = true;`).
LINE_COMMENT = {
    ".cpp": r"^\s*//", ".h": r"^\s*//", ".td": r"^\s*//", ".mim": r"^\s*//",
    ".py": r"^\s*#", ".yaml": r"^\s*#", ".yml": r"^\s*#",
}


def code_lines(text, suffix):
    """Non-blank, non-comment lines of `text`."""
    if suffix in (".cpp", ".h", ".td", ".mim"):
        text = BLOCK_COMMENT.sub("", text)
    pat = re.compile(LINE_COMMENT[suffix])
    return [l for l in text.splitlines() if l.strip() and not pat.match(l)]


def count(path, verbose=False):
    path = Path(path)
    if not path.is_file():
        sys.exit(f"missing file: {path}")
    n = len(code_lines(path.read_text(errors="replace"), path.suffix))
    if verbose:
        print(f"    {n:6d}  {path}")
    return n


def count_all(paths, verbose=False):
    return sum(count(p, verbose) for p in paths)


def count_region(path, first, last, verbose=False):
    """Lines from the first line matching `first` up to (not incl.) `last`.

    Regions are anchored on declaration names rather than line numbers so the
    script keeps working as the sources move.
    """
    path = Path(path)
    lines = path.read_text(errors="replace").splitlines()
    a = next((i for i, l in enumerate(lines) if re.match(first, l)), None)
    b = next((i for i, l in enumerate(lines) if re.match(last, l)), None)
    if a is None or b is None or a >= b:
        sys.exit(f"anchors not found in {path}: {first!r} .. {last!r}")
    n = len(code_lines("\n".join(lines[a:b]), path.suffix))
    if verbose:
        print(f"    {n:6d}  {path} [{first} .. {last})")
    return n, len(code_lines("\n".join(lines), path.suffix))


# ------------------------------------------------------ MimIR operation counts

PHASE_AXM = re.compile(r":\s*%compile\.Phase")


def annexed_operations(path, plug, skip_from, skip_to):
    """The operations a plugin exports, and its full annex list.

    An *annex* is a top-level declaration carrying the plugin's own namespace
    (`%tensor.foo`); a file-local `lam`/`let` has no such prefix and is not one.
    Of those, an *operation* is an `axm` that is neither a `%compile.Phase` nor
    part of the scheduling region, and is not an `_impl` definition of another
    axiom.  Returns (operations, annexes).
    """
    path = Path(path)
    lines = path.read_text(errors="replace").splitlines()
    a = next((i for i, l in enumerate(lines) if re.match(skip_from, l)), None)
    b = next((i for i, l in enumerate(lines) if re.match(skip_to, l)), None)
    if a is None or b is None:
        sys.exit(f"anchors not found in {path}")
    decl = re.compile(rf"^(axm|lam|let|fun) %{plug}\.([A-Za-z_0-9.()]+)")
    ops, annexes = [], []
    for i, line in enumerate(lines):
        m = decl.match(line)
        if not m or a <= i < b:            # skip the scheduling region
            continue
        kind, name = m.groups()
        if name.endswith("_impl") or PHASE_AXM.search(line):
            continue
        annexes.append(name)
        if kind == "axm":
            ops.append(name)
    return ops, annexes


# ------------------------------------------- MLIR's scf tiling driver, by job

DRIVER_FUSE = re.compile(r"[Ff]use|Consumer|Producer")
DRIVER_LOOP = re.compile(r"LoopNest|yieldTiledValues|InitOperands"
                         r"|InitialTensors|TileOffsetAndSizes|ReplaceLoop")


def split_tiling_driver(path, verbose=False):
    """Attribute every line of TileUsingInterface.cpp to one of three jobs.

    The driver entangles three things that MimIR keeps apart, so charging it
    wholesale to either row is wrong.  A function is classified by its name:
    tile-and-fuse (excluded, as fusion is excluded on both sides), loop
    generation (belongs with the other lowering), or the tiling orchestration
    itself.  File-scope lines -- includes, usings, namespaces -- go with the
    orchestration.  Returns (fusion, loopgen, orchestration).
    """
    raw = Path(path).read_text(errors="replace")
    # Blank out block comments in place so line numbers survive, then apply
    # exactly the rule code_lines() uses everywhere else.
    raw = BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), raw)
    lines = raw.splitlines()
    starts = [i for i, l in enumerate(lines)
              if re.match(r"^[A-Za-z_].*\(", l) and not l.startswith(("//", "}"))]
    tag = [None] * len(lines)
    i = 0
    while i < len(lines):
        if i in starts:
            j = i
            while j < len(lines) and not lines[j].startswith("}"):
                j += 1
            head = " ".join(lines[i:min(i + 3, len(lines))])
            k = ("fusion" if DRIVER_FUSE.search(head)
                 else "loopgen" if DRIVER_LOOP.search(head)
                 else "orchestration")
            for x in range(i, j + 1):
                tag[x] = k
            i = j
        i += 1
    out = {"fusion": 0, "loopgen": 0, "orchestration": 0}
    for i, l in enumerate(lines):
        if l.strip() and not re.match(r"^\s*//", l):
            out[tag[i] or "orchestration"] += 1
    if verbose:
        for k, n in out.items():
            print(f"    {n:6d}  {Path(path).name} ({k})")
    return out["fusion"], out["loopgen"], out["orchestration"]


# -------------------------------------------------- MLIR verifiers vs. folders

FN_DEF = re.compile(
    r"^(?:\w[\w:<>,\s\*&]*?)\b(\w+)::"
    r"(verify|verifySymbolUses|fold|getCanonicalizationPatterns)\s*\("
)
CLASS_DEF = re.compile(r"^(?:struct|class)\s+(\w+)\s*(?::|final)")


def split_verify_fold(path, verbose=False):
    """Separate LinalgOps.cpp into verifiers and folding/canonicalization.

    Entry points (`X::verify`, `X::fold`, `X::getCanonicalizationPatterns`) are
    matched at column 0 and span to the closing brace at column 0; rewrite
    pattern classes span to the closing `};`.
    """
    lines = Path(path).read_text(errors="replace").splitlines()

    def span(a, b):
        return len(code_lines("\n".join(lines[a:b]), ".cpp"))

    verify = fold = 0
    i = 0
    while i < len(lines):
        fn, cls = FN_DEF.match(lines[i]), CLASS_DEF.match(lines[i])
        if fn:
            j = i
            while j < len(lines) and not lines[j].startswith("}"):
                j += 1
            n = span(i, j + 1)
            if fn.group(2).startswith("verify"):
                verify += n
            else:
                fold += n
            i = j
        elif cls and any("RewritePattern" in lines[k]
                         for k in range(i, min(i + 3, len(lines)))):
            j = i
            while j < len(lines) and not lines[j].startswith("};"):
                j += 1
            fold += span(i, j + 1)
            i = j
        i += 1
    if verbose:
        print(f"    {verify:6d}  {path} (verifiers)")
        print(f"    {fold:6d}  {path} (fold + canonicalization patterns)")
    return verify, fold


# ------------------------------------------- feature-matched "define" row

# Each MimIR operation of tensor/btensor that has a linalg counterpart, with
# the .mim sections (see mim_sections) that define it and the linalg named ops
# it corresponds to: its direct counterparts, and the linalg ops whose
# functionality it subsumes (e.g. linalg.exp is %tensor.unary applied to
# %math.exp).  MimIR's conv and pool are 2-D NCHW
# without groups, so linalg's other layouts, depthwise, 1-D/3-D and quantized
# variants count as uncovered.  MimIR ops without a linalg counterpart (pad,
# slice, gather, reshape, ...) belong to MLIR's tensor dialect, which the
# define row does not count, and are left out on both sides.
UNARY = "exp log abs ceil floor negf reciprocal round sqrt rsqrt square tanh erf"
BINARY = "add sub mul div div_unsigned max min powf"
MATCH = [
    # MimIR sections                                     direct         subsumed linalg ops
    (("tensor.map_reduce_post", "btensor.map_reduce_post",
      "btensor.map_reduce"),                             "generic reduce", ""),
    (("tensor.map",),                                    "map",         ""),
    (("tensor.unary", "tensor.binary"),                  "elementwise", UNARY + " " + BINARY),
    (("tensor.select",),                                 "select",      ""),
    (("tensor.splat",),                                  "fill",        ""),
    (("tensor.conv",),                                   "conv_2d_nchw_fchw", ""),
    (("tensor.pool",),                                   "pooling_nchw_max", "pooling_nchw_sum"),
    (("tensor.dot_product",),                            "contract",    "dot matvec vecmat batch_matvec batch_vecmat batch_reduce_matmul"),
    (("tensor.product_2d", "btensor.product_2d"),        "matmul",      ""),
    (("tensor.bmm",),                                    "batch_matmul", ""),
    (("tensor.transpose", "tensor.transpose_2d",
      "btensor.transpose_2d"),                           "transpose",   ""),
    (("tensor.broadcast", "tensor.broadcast_in_dim",
      "btensor.broadcast"),                              "broadcast",   ""),
]
# Sections shared by all operations of a plugin: imports, the Ring type, phases.
MIM_SHARED = ("tensor:Dependencies", "tensor.Ring", "tensor:Phases",
              "btensor:Dependencies", "btensor.Ring", "btensor:Phases")


def linalg_sections(L):
    """Code lines of linalg's define row, per named op plus a shared remainder.

    An op's lines are its `@linalg_structured_op` function in the opdsl
    script, its `--- !LinalgOpConfig` document in the generated YAML, and its
    `def` in LinalgStructuredOps.td.  Everything else is shared.
    """
    ops, shared = {}, 0
    py = (L / "python/mlir/dialects/linalg/opdsl/ops/core_named_ops.py").read_text()
    parts = re.split(r"\n(?=@linalg_structured_op)", py)
    shared += len(code_lines(parts[0], ".py"))
    for p in parts[1:]:
        name = re.search(r"^def (\w+)", p, re.M).group(1)
        ops[name] = ops.get(name, 0) + len(code_lines(p, ".py"))
    yaml = (L / "include/mlir/Dialect/Linalg/IR/"
            "LinalgNamedStructuredOps.yaml").read_text()
    parts = re.split(r"\n(?=--- !LinalgOpConfig)", yaml)
    shared += len(code_lines(parts[0], ".yaml"))
    for p in parts[1:]:
        name = re.search(r"^  name: (\S+)", p, re.M).group(1)
        ops[name] = ops.get(name, 0) + len(code_lines(p, ".yaml"))
    td = BLOCK_COMMENT.sub("", (L / "include/mlir/Dialect/Linalg/IR/"
                                "LinalgStructuredOps.td").read_text())
    for p in re.split(r"\n(?=def |class |//===)", td):
        n = len(code_lines(p, ".td"))
        m = re.match(r'def \w+\s*:\s*\w+<"(\w+)"', p)
        if m:
            ops[m.group(1)] = ops.get(m.group(1), 0) + n
        else:
            shared += n
    return ops, shared


def mim_sections(path, plug, skip_from, skip_to):
    """Code lines of a .mim plugin outside the scheduling region, per section.

    A section starts at a `/// ### %%plug.op` heading, or at an `axm %plug.op`
    whose heading lies inside the skipped region.  Non-operation headings
    (`## Dependencies`, ...) are keyed as `plug:Heading`.
    """
    lines = Path(path).read_text(errors="replace").splitlines()
    a = next(i for i, l in enumerate(lines) if re.match(skip_from, l))
    b = next(i for i, l in enumerate(lines) if re.match(skip_to, l))
    out, cur = {}, None
    for i, l in enumerate(lines):
        if a <= i < b:
            continue
        h = re.match(r"^/// #+ (?:%%)?(\S+)", l)
        x = re.match(rf"^axm %({plug}\.\w+)", l)
        if h:
            cur = h.group(1) if "." in h.group(1) else f"{plug}:{h.group(1)}"
        elif x and x.group(1) != cur:
            cur = x.group(1)
        out.setdefault(cur, []).append(l)
    return {k: len(code_lines("\n".join(v), ".mim")) for k, v in out.items()}


def feature_matched(L, P, verbose=False):
    lin, lin_shared = linalg_sections(L)
    mim = {**mim_sections(P / "tensor/tensor.mim", "tensor",
                          r"^let SchedT", r"^axm %tensor\.repeat"),
           **mim_sections(P / "btensor/btensor.mim", "btensor",
                          r"^lam ForT", r"^axm %btensor\.map_reduce_post")}
    one = [o for _, d, _ in MATCH for o in d.split()]
    cov = one + [o for _, _, s in MATCH for o in s.split()]
    for o in cov:
        if o not in lin:
            sys.exit(f"linalg op not found: {o}")
    secs = [s for ss, _, _ in MATCH for s in ss] + list(MIM_SHARED)
    for s in secs:
        if s not in mim:
            sys.exit(f"mim section not found: {s}")
    ops = []
    for src, plug, first, last in (
        (P / "tensor/tensor.mim", "tensor", r"^let SchedT", r"^axm %tensor\.repeat"),
        (P / "btensor/btensor.mim", "btensor", r"^lam ForT", r"^axm %btensor\.map_reduce_post"),
    ):
        ops += [f"{plug}.{o}" for o in annexed_operations(src, plug, first, last)[0]]
    r = {
        "matched.ops.mlir": len(one),
        "matched.ops.mimir": len([o for o in ops if o in secs]),
        "matched.mlir": sum(lin[o] for o in one) + lin_shared,
        "matched.mimir": sum(mim[s] for s in secs),
        "covered.ops": len(cov),
        "covered.mlir": sum(lin[o] for o in cov) + lin_shared,
        # sanity check: the per-op split partitions the define row
        "info.define.mlir.split": sum(lin.values()) + lin_shared,
        "info.define.mimir.split": sum(mim.values()),
    }
    r["matched.mlir.per_op"] = round(r["matched.mlir"] / r["matched.ops.mlir"])
    r["matched.mimir.per_op"] = round(r["matched.mimir"] / r["matched.ops.mimir"])
    if verbose:
        print(f"    {lin_shared:6d}  linalg (shared)")
        for ss, d, s in MATCH:
            print(f"    {sum(lin[o] for o in d.split()):6d}  linalg.{d:<20} "
                  f"{sum(mim[x] for x in ss):6d}  {', '.join(ss)}")
            for x in s.split():
                print(f"    {lin[x]:6d}  linalg.{x} (subsumed)")
        print(f"    {'':6}  {'':27} {sum(mim[x] for x in MIM_SHARED):6d}  (shared)")
    return r


# ------------------------------------------------------------------ the counts

def revision(repo):
    try:
        return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                              capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return "<not a git checkout>"


def collect(mlir, mimir, verbose):
    m, i = Path(mlir), Path(mimir)
    L = m / "mlir"
    P = i / "src/mim/plug"
    v = verbose
    r = {}

    def hdr(s):
        if v:
            print(f"\n  {s}")

    # --- define -------------------------------------------------------------
    # MLIR: linalg's 81 named structured ops, described in Python, generated to
    # YAML, declared in TableGen.  MimIR: everything in the two .mim sources
    # that is not the schedule library / nest algebra.
    hdr("define (MLIR)")
    r["define.mlir"] = count_all([
        L / "python/mlir/dialects/linalg/opdsl/ops/core_named_ops.py",
        L / "include/mlir/Dialect/Linalg/IR/LinalgNamedStructuredOps.yaml",
        L / "include/mlir/Dialect/Linalg/IR/LinalgStructuredOps.td",
    ], v)

    hdr("define (MimIR) = .mim total - scheduling region")
    sched_t, tensor_total = count_region(
        P / "tensor/tensor.mim", r"^let SchedT", r"^axm %tensor\.repeat", v)
    nest_b, btensor_total = count_region(
        P / "btensor/btensor.mim", r"^lam ForT",
        r"^axm %btensor\.map_reduce_post", v)
    r["define.mimir"] = (tensor_total - sched_t) + (btensor_total - nest_b)

    # --- verify / fold ------------------------------------------------------
    # Verification is deliberately not a row.  MLIR's verifiers are separable
    # (the figure below), but MimIR's checking is spread across the type
    # checker, static-ness gates and refly.check sites that no file boundary
    # captures, so there is no honest counterpart to compare against.
    hdr("fold (MLIR); the verifier figure is informational, not a row")
    r["info.verify.mlir"], r["fold.mlir"] = split_verify_fold(
        L / "lib/Dialect/Linalg/IR/LinalgOps.cpp", v)

    hdr("fold (MimIR): normalizers")
    r["fold.mimir"] = count_all([
        P / "tensor/normalizers.cpp",
        P / "btensor/normalizers.cpp",
    ], v)

    # --- lower --------------------------------------------------------------
    # Only the path the standard pipeline in opt.mim actually takes:
    #   %tensor.lower_tensor  ->  %btensor.lower_map_reduce
    # The tensor plugin's own direct map_reduce lowering is never run.
    # MLIR emits loops from two places: Loops.cpp for the untiled path and
    # the scf driver for a tiled domain.  Both are counted -- MimIR's single
    # btensor phase serves both cases and is counted below.
    hdr("lower to a loop nest (MLIR): both paths")
    fuse_n, loopgen_n, orch_n = split_tiling_driver(
        L / "lib/Dialect/SCF/Transforms/TileUsingInterface.cpp", v)
    r["info.driver_fusion"] = fuse_n
    r["lower.mlir"] = count_all(
        [L / "lib/Dialect/Linalg/Transforms/Loops.cpp"], v) + loopgen_n

    hdr("lower to a loop nest (MimIR): the phases opt.mim runs")
    r["lower.mimir"] = count_all([
        P / "tensor/phase/lower.cpp",              # %tensor.lower_tensor
        P / "btensor/phase/lower_map_reduce.cpp",  # %btensor.lower_map_reduce
    ], v)

    # --- affine maps --------------------------------------------------------
    hdr("affine maps (MLIR)")
    r["affine.mlir"] = count_all([
        L / "include/mlir/IR/AffineExpr.h",
        L / "include/mlir/IR/AffineMap.h",
        L / "lib/IR/AffineExpr.cpp",
        L / "lib/IR/AffineMap.cpp",
        L / "lib/IR/AffineExprDetail.h",
        L / "lib/IR/AffineMapDetail.h",
        L / "lib/AsmParser/AffineParser.cpp",
    ], v)

    # Lowering an affine map to index arithmetic is excluded on both sides,
    # like every other lowering here; counting MimIR's and not MLIR's was what
    # made this row look like it needed two languages.
    hdr("affine maps (MimIR)")
    r["affine.mimir"] = count_all([P / "affine/affine.mim"], v)

    # The lowerings that follow a loop nest are excluded on both sides.  Each
    # framework stops at emitting the loop construct -- scf.for / affine.for on
    # one side, %affine.For on the other -- and expanding it into branches, and
    # expanding an affine map into index arithmetic, come after.
    hdr("post-loop-nest lowerings (excluded on both sides)")
    r["info.affine_lowering.mlir"] = count_all(
        [L / "lib/Conversion/AffineToStandard/AffineToStandard.cpp"], v)
    r["info.affine_lowering.mimir"] = count_all(
        [P / "affine/phase/lower_index.cpp"], v)
    r["info.cf_lowering.mlir"] = count_all(
        [L / "lib/Conversion/SCFToControlFlow/SCFToControlFlow.cpp"], v)
    r["info.cf_lowering.mimir"] = count_all(
        [P / "affine/phase/lower_for.cpp"], v)

    # --- tiling -------------------------------------------------------------
    # scf's generic tiling driver is NOT counted here.  A third of it
    # implements tile-and-fuse, and fusion is excluded on MimIR's side; the
    # rest emits the loops, whose MimIR counterpart is the btensor phase
    # already charged to the "lower" row.  Counting it would bill MLIR twice.
    hdr("tiling (MLIR): interface, implementations, driver orchestration")
    r["tiling.mlir"] = count_all([
        L / "include/mlir/Interfaces/TilingInterface.td",
        L / "lib/Interfaces/TilingInterface.cpp",
        L / "lib/Dialect/Linalg/Transforms/Tiling.cpp",
        L / "lib/Dialect/Linalg/Transforms/TilingInterfaceImpl.cpp",
        L / "lib/Dialect/Tensor/IR/TensorTilingInterfaceImpl.cpp",
        L / "include/mlir/Dialect/SCF/Transforms/TileUsingInterface.h",
    ], v) + orch_n

    hdr("tiling (MimIR) = schedule library + nest algebra")
    if v:
        print(f"    {sched_t:6d}  tensor.mim [schedule library]")
        print(f"    {nest_b:6d}  btensor.mim [nest algebra]")
    r["tiling.mimir"] = sched_t + nest_b

    # --- denominators and footnote figures ----------------------------------
    yaml = (L / "include/mlir/Dialect/Linalg/IR/"
            "LinalgNamedStructuredOps.yaml").read_text()
    r["linalg.named_ops"] = yaml.count("\n--- !LinalgOpConfig")

    hdr("the operations the define row defines")
    ax, ann = [], []
    for src, plug, first, last in (
        (P / "tensor/tensor.mim", "tensor",
         r"^let SchedT", r"^axm %tensor\.repeat"),
        (P / "btensor/btensor.mim", "btensor",
         r"^lam ForT", r"^axm %btensor\.map_reduce_post"),
    ):
        a, n = annexed_operations(src, plug, first, last)
        ax += a
        ann += n
        if v:
            print(f"    {len(a):6d}  {src.name}: {', '.join(a)}")
    # The denominator is the plugin's *operation* surface: annexed axioms that
    # are neither a compiler phase nor part of the scheduling region.  Annexed
    # helpers and types (Ring, id, mk_sched, proj_map, reshape_map) are not
    # operations and are excluded, which is the conservative choice -- counting
    # them would lower the per-operation figure.
    r["tensor.operations"] = len(ax)
    r["tensor.annexes"] = len(ann)
    # Reported separately in the text: how many of those have a Mim definition
    # that lowering merely beta-reduces.
    r["tensor.defined_in_mim"] = (
        P / "tensor/phase/lower.cpp").read_text().count("lower_via_impl(app,")

    r["define.mlir.per_op"] = round(r["define.mlir"] / r["linalg.named_ops"])
    r["define.mimir.per_op"] = round(r["define.mimir"] / r["tensor.operations"])

    hdr("define, feature-matched: linalg op vs. its MimIR counterpart")
    r.update(feature_matched(L, P, v))
    for k in ("mlir", "mimir"):
        if r[f"info.define.{k}.split"] != r[f"define.{k}"]:
            sys.exit(f"per-op split of the define row does not add up ({k})")

    hdr("excluded: the tensor plugin's direct lowering (never run)")
    r["excluded.direct_lowering"] = count_all([
        P / "tensor/phase/lower_map_reduce.cpp",
        P / "tensor/phase/lower_get_set.cpp",
    ], v)

    hdr("all C++ in the tensor and btensor plugins")
    cpp = sorted([f for d in ("tensor", "btensor")
                  for f in (P / d).rglob("*")
                  if f.suffix in (".cpp", ".h")])
    r["total.mimir_cpp"] = count_all(cpp, v)
    return r


ROWS = [
    ("Define {a} vs. {b} operations", "define", 3, 1),
    ("Fold and canonicalize",         "fold",   1, 1),
    ("Lower them to a loop nest",     "lower",  1, 1),
    ("Affine maps",                   "affine", 1, 1),
    ("Tiling and scheduling",         "tiling", 2, 1),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mlir", required=True, help="path to an llvm-project checkout")
    ap.add_argument("--mimir", required=True, help="path to a mimir checkout")
    ap.add_argument("--check", action="store_true",
                    help="compare against the values printed in the paper")
    ap.add_argument("--verbose", "-v", action="store_true",
                    help="show the per-file breakdown of every row")
    a = ap.parse_args()

    for name, repo, want in (("MLIR", a.mlir, MLIR_REV), ("MimIR", a.mimir, MIMIR_REV)):
        got = revision(repo)
        mark = "" if got.startswith(want) or want.startswith(got[:10]) else \
               f"  << differs from the revision in the paper ({want[:10]})"
        print(f"{name:6s} {repo}  @ {got[:12]}{mark}")

    r = collect(a.mlir, a.mimir, a.verbose)

    print(f"\nTable 1 -- what one job costs"
          f"  ({r['linalg.named_ops']} linalg named ops;"
          f" {r['tensor.operations']} Mim operations of {r['tensor.annexes']}"
          f" annexes, {r['tensor.defined_in_mim']} with a Mim definition)\n")
    print(f"  {'Job':<32}{'MLIR':>8} {'lang':>5}{'MimIR':>8} {'lang':>5}")
    print("  " + "-" * 58)
    for label, key, lm, li in ROWS:
        label = label.format(a=r["linalg.named_ops"], b=r["tensor.operations"])
        print(f"  {label:<32}{r[key+'.mlir']:>8} {lm:>5}"
              f"{r[key+'.mimir']:>8} {li:>5}")
        if key == "define":
            print(f"  {'  per operation':<32}{r['define.mlir.per_op']:>8} "
                  f"{'':>5}{r['define.mimir.per_op']:>8}")
            print(f"  {'  matched, {} vs. {} ops'.format(r['matched.ops.mlir'], r['matched.ops.mimir']):<32}"
                  f"{r['matched.mlir']:>8} {'':>5}{r['matched.mimir']:>8}")
            print(f"  {'  per operation':<32}{r['matched.mlir.per_op']:>8} "
                  f"{'':>5}{r['matched.mimir.per_op']:>8}")
            print(f"  {'  all {} linalg ops covered'.format(r['covered.ops']):<32}"
                  f"{r['covered.mlir']:>8} {'':>5}{r['matched.mimir']:>8}")
    print(f"\n  Not a row / footnote / text:")
    print(f"    MLIR verifiers in LinalgOps.cpp  "
          f"{r['info.verify.mlir']:>6}")
    print(f"    scf driver tile-and-fuse (excl.) "
          f"{r['info.driver_fusion']:>6}")
    print(f"    excluded AffineToStandard / lower_index  "
          f"{r['info.affine_lowering.mlir']:>4}"
          f" / {r['info.affine_lowering.mimir']}")
    print(f"    excluded SCFToControlFlow / lower_for    "
          f"{r['info.cf_lowering.mlir']:>4}"
          f" / {r['info.cf_lowering.mimir']}")
    print(f"    excluded, never run by opt.mim   {r['excluded.direct_lowering']:>6}")
    print(f"    all C++ in tensor + btensor      {r['total.mimir_cpp']:>6}")

    if a.check:
        bad = {k: (v, EXPECTED[k]) for k, v in r.items()
               if k in EXPECTED and v != EXPECTED[k]}
        if bad:
            print("\nMISMATCH against the published values:")
            for k, (got, want) in sorted(bad.items()):
                print(f"    {k:<32} got {got}, paper says {want}")
            return 1
        print(f"\nall {len(EXPECTED)} published values reproduced")
    return 0


if __name__ == "__main__":
    sys.exit(main())
