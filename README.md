# MimIR KernelBench artifact (Docker)

Builds one image that contains everything needed to reproduce the KernelBench
level-3 comparison of MimIR (mimir-frontend, LLVM and MLIR paths) against
torch-mlir, and the pipeline that runs it (`benchmark/`).

The image reproduces the toolchain of the machine the results were produced
on. That machine runs Manjaro (Arch-based), so the image is Arch Linux pinned to
the **Arch Linux Archive snapshot of 2026-10-03**, whose packages match it
exactly:

| package | version (host = image) | used for |
|---|---|---|
| gcc | 16.2.1+r23+gd564253eb6c8 | LLVM/MLIR, MimIR (as on the host) |
| clang / llvm / lld / compiler-rt | 23.1.1 | C drivers, MimIR's JIT, torch-mlir |
| cmake / ninja | 4.4.4 / 1.13.2 | builds |
| python | 3.14.7 | mimir-frontend venv |
| glibc | 2.44+r50 | |

Built from source on top of that, at pinned commits:

| component | version | notes |
|---|---|---|
| LLVM + MLIR | `068c6c5c0c8a` (23.0.0git) | host options: Release + assertions, no RTTI, X86;NVPTX, Python bindings; tests not built |
| torch-mlir | `4cf2188eb848` | against that LLVM, Python 3.12.12 (as the host venv) |
| PyTorch (torch-mlir side) | `2.14.0+cpu` | see below |
| mimir-frontend | `HarithF/mimir-frontend`, branch `art-eval` | cloned at build time |
| MimIR + plugins | the frontend's submodule pin; plugins at the refs in `bootstrap_mimir.sh` | |
| benchmark | `HarithF/mim_benchmark`, branch `main` | cloned at build time |

The LLVM commit is the one torch-mlir pins at that commit; the same
`mlir-opt`/`opt`/`llc` build lowers and compiles all three variants, and is
first on PATH, as on the host.

Two differences from the host remain, both only in how torch-mlir is built:
- **PyTorch:** torch-mlir `4cf2188eb848` names the nightly
  `torch==2.14.0.dev20260719`, which the nightly index no longer serves. The
  image uses the `2.14.0` release of that line instead.
- **Compiler:** the host's torch-mlir was compiled with clang 22.1.8, which
  can't sit next to clang 23.1.1 in the snapshot.

Both only affect the exporter, and its output is verified to be identical (see
"Verification").

## Build

```bash
./build.sh                                   # docker build -t mimir .
FRONTEND_REF=my-branch BENCH_REF=main ./build.sh   # other branches
FRONTEND_REPO=someone/mimir-frontend ./build.sh    # or a fork
JOBS=12 LINK_JOBS=2 ./build.sh               # compile / link parallelism
```

The image clones mimir-frontend and benchmark from GitHub, so it builds what is
pushed, not local changes. Each repository's (and each plugin's) current head
commit is fetched first, so after a push the next build re-clones exactly what
changed and reuses the cached layers before it -- LLVM and torch-mlir are not
rebuilt.
- Stage 1 clones and builds LLVM/MLIR and torch-mlir.
- Stage 2 clones mimir-frontend, runs its `bootstrap_mimir.sh` (MimIR, the
  plugins, the Python 3.14 venv) and clones benchmark.

Requirements: network access (GitHub, the Arch Linux Archive, PyPI,
download.pytorch.org), roughly 50 GB of free disk for the build (about 15 GB
remain as the image), and time: LLVM, MLIR and torch-mlir take about an hour
on 16 cores, the mimir-frontend bootstrap (including its PyTorch download)
another half hour or so.

## Run

```bash
./run.sh                         # (host) shell in a new container "mimir-run"
# inside the container (working dir: ~/benchmark):
./run.sh                         # export -> build -> report, all 36 models
./run.sh all --only "1_MLP 4_LeNet5"
./run.sh report                  # timings only, once built
```

Results land in `~/benchmark/work/` (see `benchmark/README.md`); copy them out
with `docker cp mimir-run:/home/bench/benchmark/work/reports .`.
Resume a container with `docker start -ai mimir-run`.

Timing runs should be pinned (`PIN_CPU`, default core 2) and, ideally, run with
the host's CPU governor set to `performance`.

## Layout

```
Dockerfile        stage 1: LLVM/MLIR + torch-mlir; stage 2: mimir-frontend + benchmark
build.sh          docker build (repositories and branches as build arguments)
run.sh            docker run wrapper
save.sh           docker save -> mimir.tar.gz
```

## Verification

- **torch 2.14.0 vs the pinned nightly:** all 50 level-3 models exported with
  `2.14.0+cpu` (Python 3.12, same torch-mlir build, same `export_mlir.py`) are
  byte-identical to the exports made with `2.14.0.dev20260719+cpu`: every
  `.mlir` and every `.params.txt`, 50 of 50.
- **torch-mlir built with clang 23.1.1 (image) vs 22.1.8 (host):** the 36
  benchmark models exported inside the image are byte-identical to the host's
  exports (`.mlir` and `.params.txt`).
- **Toolchain inside the image:** gcc 16.2.1, clang 23.1.1, `opt`/`mlir-opt`
  23.0.0git first on PATH, Python 3.14.7 -- as on the host.
- **Pipeline inside the image:** `./run.sh all` on LeNet5 and MiniGPTBlock --
  export, build and report -- passes; every variant matches the PyTorch
  reference. On the host, the same pipeline passes on LeNet5, VisionTransformer,
  SwinTransformerV2, MiniGPTBlock and ReLUSelfAttention, which between them
  cover every special case (collapsed unit dims, libm math, integer buffers,
  closure-captured parameters, parameters only torch-mlir passes).
