# syntax=docker/dockerfile:1
#
# KernelBench level-3: MimIR (LLVM and MLIR paths) vs torch-mlir (benchmark/).
# Arch Linux pinned to the 2026-10-03 archive snapshot, whose toolchain matches
# the host exactly (gcc 16.2.1, clang 23.1.1, python 3.14.7). Built from source:
#   stage 1  LLVM/MLIR and torch-mlir at pinned commits
#   stage 2  mimir-frontend (+ MimIR) and benchmark, cloned from GitHub, and
#            the tools from stage 1

ARG ARCH_SNAPSHOT=2026/10/03
ARG LLVM_COMMIT=068c6c5c0c8a0555036a2ff09a99f486548e6e8d
ARG TORCH_MLIR_COMMIT=4cf2188eb84896772e771610eed44b3d49f0af80
# The pinned nightly (2.14.0.dev20260719) is no longer served; the 2.14.0
# release exports identically.
ARG TORCH_VERSION=2.14.0
ARG PYTHON_TORCH_MLIR=3.12.12
# The repositories stage 2 clones (owner/name on GitHub, branch).
ARG FRONTEND_REPO=HarithF/mimir-frontend
ARG FRONTEND_REF=art-eval
ARG BENCH_REPO=HarithF/mim_benchmark
ARG BENCH_REF=main

##############################################################################
# Base: Arch Linux at the pinned snapshot
##############################################################################
FROM archlinux:base AS base
ARG ARCH_SNAPSHOT
RUN echo "Server = https://archive.archlinux.org/repos/${ARCH_SNAPSHOT}/\$repo/os/\$arch" > /etc/pacman.d/mirrorlist \
 && sed -i 's/^NoExtract.*//' /etc/pacman.conf \
 && pacman -Syyuu --noconfirm \
 && pacman -S --noconfirm --needed \
      base-devel gcc clang llvm lld compiler-rt cmake ninja git ca-certificates curl \
      python uv rsync sudo which zlib zstd libxml2 libedit ncurses util-linux \
 && pacman -Scc --noconfirm \
 && gcc --version | head -1 && clang --version | head -1 && python --version

##############################################################################
# Stage 1: LLVM/MLIR + torch-mlir
##############################################################################
FROM base AS toolchain
ARG LLVM_COMMIT
ARG TORCH_MLIR_COMMIT
ARG TORCH_VERSION
ARG PYTHON_TORCH_MLIR
ARG JOBS=
ARG LINK_JOBS=2

# One Python 3.12 venv for both builds and for running torch-mlir; the
# interpreter lives in /opt/python so stage 2 can copy it.
ENV UV_PYTHON_INSTALL_DIR=/opt/python
RUN uv venv --python ${PYTHON_TORCH_MLIR} /opt/torch-venv
ENV VIRTUAL_ENV=/opt/torch-venv PATH=/opt/torch-venv/bin:$PATH
RUN uv pip install --no-cache "nanobind>=2.9,<3.0" "pybind11>=2.10" "PyYAML>=5.4.0" "typing_extensions>=4.12.2" \
      "numpy==2.5.2" "ml_dtypes==0.6.0" "packaging==26.3" "einops==0.8.2" \
 && uv pip install --no-cache "torch==${TORCH_VERSION}+cpu" \
      --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple \
      --index-strategy unsafe-best-match

# --- LLVM/MLIR at the commit torch-mlir pins (Release, no assertions; no tests) --
RUN git init -q /opt/llvm-project \
 && git -C /opt/llvm-project fetch -q --depth 1 https://github.com/llvm/llvm-project.git ${LLVM_COMMIT} \
 && git -C /opt/llvm-project checkout -q FETCH_HEAD
RUN cmake -G Ninja -S /opt/llvm-project/llvm -B /opt/llvm-project/build \
      -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_C_COMPILER=gcc -DCMAKE_CXX_COMPILER=g++ \
      -DLLVM_PARALLEL_LINK_JOBS=${LINK_JOBS} \
      -DLLVM_ENABLE_PROJECTS=mlir \
      -DLLVM_TARGETS_TO_BUILD="X86;NVPTX" \
      -DLLVM_ENABLE_ASSERTIONS=OFF \
      -DLLVM_ENABLE_RTTI=OFF \
      -DLLVM_INCLUDE_TESTS=OFF -DMLIR_INCLUDE_TESTS=OFF \
      -DLLVM_INCLUDE_BENCHMARKS=OFF -DLLVM_INCLUDE_EXAMPLES=OFF \
      -DMLIR_ENABLE_BINDINGS_PYTHON=ON \
      -DMLIR_ENABLE_EXECUTION_ENGINE=ON \
      -DPython3_EXECUTABLE=/opt/torch-venv/bin/python \
 && cmake --build /opt/llvm-project/build ${JOBS:+-j ${JOBS}}

# --- torch-mlir against that build --------------------------------------------
# clang (StableHLO needs it) and Python_EXECUTABLE (else the bindings target
# Python 3.14), as on the host. No link-job setting: inherited from LLVM.
RUN git init -q /opt/torch-mlir \
 && git -C /opt/torch-mlir fetch -q --depth 1 https://github.com/llvm/torch-mlir.git ${TORCH_MLIR_COMMIT} \
 && git -C /opt/torch-mlir checkout -q FETCH_HEAD \
 && git -C /opt/torch-mlir submodule update -q --init --depth 1 externals/stablehlo
RUN cmake -G Ninja -S /opt/torch-mlir -B /opt/torch-mlir/build \
      -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
      -DPython3_EXECUTABLE=/opt/torch-venv/bin/python -DPython_EXECUTABLE=/opt/torch-venv/bin/python \
      -DLLVM_DIR=/opt/llvm-project/build/lib/cmake/llvm \
      -DMLIR_DIR=/opt/llvm-project/build/lib/cmake/mlir \
      -DTORCH_MLIR_ENABLE_STABLEHLO=ON \
      -DTORCH_MLIR_ENABLE_JIT_IR_IMPORTER=ON \
      -DTORCH_MLIR_ENABLE_LTC=OFF \
 && cmake --build /opt/torch-mlir/build --target TorchMLIRPythonModules ${JOBS:+-j ${JOBS}}

# Gather what stage 2 needs (torch-mlir with symlinks resolved).
RUN mkdir -p /opt/llvm/bin /opt/llvm/lib \
 && cp /opt/llvm-project/build/bin/mlir-opt /opt/llvm-project/build/bin/mlir-translate \
       /opt/llvm-project/build/bin/mlir-runner /opt/llvm-project/build/bin/opt \
       /opt/llvm-project/build/bin/llc /opt/llvm-project/build/bin/llvm-link \
       /opt/llvm-project/build/bin/FileCheck /opt/llvm/bin/ \
 && cp -a /opt/llvm-project/build/lib/libmlir_c_runner_utils.so* \
          /opt/llvm-project/build/lib/libmlir_runner_utils.so* /opt/llvm/lib/ \
 && cp -rL /opt/torch-mlir/build/python_packages/torch_mlir /opt/torch-mlir-python \
 && echo /opt/torch-mlir-python > "$(/opt/torch-venv/bin/python -c 'import site; print(site.getsitepackages()[0])')/torch_mlir.pth" \
 && /opt/torch-venv/bin/python -c "import torch, torch_mlir; from torch_mlir import fx; print('torch', torch.__version__, '+ torch_mlir ok')"

##############################################################################
# Stage 2: runtime image
##############################################################################
FROM base
ARG FRONTEND_REPO
ARG FRONTEND_REF
ARG BENCH_REPO
ARG BENCH_REF

COPY --from=toolchain /opt/llvm /opt/llvm
COPY --from=toolchain /opt/python /opt/python
COPY --from=toolchain /opt/torch-venv /opt/torch-venv

# The pinned opt/llc/mlir-* first on PATH, as on the host.
ENV PATH=/opt/llvm/bin:$PATH \
    LLVM_LIB_DIR=/opt/llvm/lib \
    TORCH_MLIR_PY=/opt/torch-venv/bin/python \
    PYTHON=/opt/torch-venv/bin/python

RUN useradd -m -u 1000 -s /bin/bash bench \
 && echo "bench ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/bench
USER bench
WORKDIR /home/bench

# --- MimIR + mimir-frontend (bootstrap_mimir.sh; needs network) ---------------
# Each ADD fetches a branch's current head commit, so a push to the frontend or
# to a plugin bootstrap fetches (refs as in bootstrap_mimir.sh) re-runs the clone.
ADD https://api.github.com/repos/${FRONTEND_REPO}/commits/${FRONTEND_REF} /tmp/heads/frontend.json
ADD https://api.github.com/repos/HarithF/mimir-torch-plugin/commits/art-eval /tmp/heads/torch.json
ADD https://api.github.com/repos/hsqStephenZhang/mimir-runtime-plugin/commits/feat/ll-emit /tmp/heads/runtime.json
ADD https://api.github.com/repos/HarithF/mim_mlir/commits/mimir-frontend-dev /tmp/heads/mim_mlir.json
ARG MIMIR_BUILD_JOBS=8
RUN chmod -R 777 /home/bench \
 && git clone -q --recursive --branch ${FRONTEND_REF} https://github.com/${FRONTEND_REPO}.git mimir-frontend \
 && cd mimir-frontend \
 && MIMIR_BUILD_JOBS=${MIMIR_BUILD_JOBS} ./scripts/bootstrap_mimir.sh \
 && cmake --build MimIR/build -j ${MIMIR_BUILD_JOBS} \
 && uv run --no-sync python -c "import mim, mimir_frontend.backend; print('mimir-frontend ok')"

# --- dependencies of the MLIR runner utilities ----------------------------------
COPY --from=toolchain /opt/llvm-project/build/lib/libmlir_apfloat_wrappers.so* \
                      /opt/llvm-project/build/lib/libmlir_float16_utils.so* /opt/llvm/lib/

# --- torch-mlir (after the bootstrap, so changes here keep it cached) -----------
COPY --from=toolchain /opt/torch-mlir-python /opt/torch-mlir-python
RUN $TORCH_MLIR_PY -c "import torch, torch_mlir; from torch_mlir import fx; print('torch', torch.__version__, '+ torch_mlir ok')" \
 && for l in /opt/llvm/lib/libmlir_c_runner_utils.so /opt/llvm/lib/libmlir_runner_utils.so; do \
      ! ldd "$l" | grep -q "not found" || { ldd "$l"; exit 1; }; done && echo "runner utils ok"

# --- benchmark pipeline ----------------------------------------------------------
ADD https://api.github.com/repos/${BENCH_REPO}/commits/${BENCH_REF} /tmp/heads/benchmark.json
RUN git clone -q --branch ${BENCH_REF} https://github.com/${BENCH_REPO}.git benchmark \
 && cd benchmark && for f in run.sh pipeline/*.sh scripts/*.sh; do bash -n "$f"; done \
 && cd scripts && $PYTHON -c "import gen_data, gen_drivers, reporter, produce_refs, param_manifest; print('benchmark scripts ok')"

WORKDIR /home/bench/benchmark
CMD ["/bin/bash", "-c", "cat <<'EOF'\n\
KernelBench level-3: MimIR (LLVM, MLIR) vs torch-mlir\n\
\n\
  ./run.sh                          export -> build -> report, all models in models.txt\n\
  ./run.sh export                   MimIR frontend + torch-mlir export\n\
  ./run.sh build                    import, data, lower, drivers, compile, references\n\
  ./run.sh report                   run all variants, compare with PyTorch, timings\n\
  ./run.sh all --only \"1_MLP 4_LeNet5\" a subset\n\
\n\
Outputs: work/ (models/NN_Model/bin/, reports/<run_id>/timing.csv). See README.md.\n\
EOF\n\
exec /bin/bash"]
