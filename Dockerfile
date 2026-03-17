# Use the latest Ubuntu LTS base image
FROM ubuntu:25.10

# Avoid interactive prompts during package installs
ENV DEBIAN_FRONTEND=noninteractive

# Update packages and install basic utilities
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        sudo \
        gdb \
        ca-certificates \
        curl \
        cmake \
        git \
        neovim \
        gcc-15 \
        g++-15 \
        llvm-21 \
        llvm-21-tools \
        clang-21 \
        graphviz \
        doxygen \
        texlive \
        texlive-latex-extra \
        python3-pandas \
        python3-psutil \
        python3-pip \
        bash && \
    rm -rf /var/lib/apt/lists/* && \
    pip3 install --break-system-packages lit && \
    ln -s /usr/bin/gcc-15 /usr/local/bin/gcc && \
    ln -s /usr/bin/g++-15 /usr/local/bin/g++ && \
    ln -s /usr/bin/clang-15 /usr/local/bin/clang && \
    ln -s /usr/bin/clang++-15 /usr/local/bin/clang++ && \
    ln -s /usr/bin/FileCheck-21 /usr/local/bin/FileCheck && \
    ln -s /usr/bin/opt-21 /usr/local/bin/opt

# create pldi user
RUN useradd -m pldi
USER pldi
WORKDIR /home/pldi

# install Lean
RUN curl https://elan.lean-lang.org/elan-init.sh -sSf | sh -s -- -y

ENV PATH="/home/pldi/.elan/bin:${PATH}"

RUN elan default stable
RUN lean --version && lake --version

# prepare repos
COPY --chown=pldi:pldi mim /home/pldi/mim/
COPY --chown=pldi:pldi lambda-graph/ /home/pldi/lambda-graph/

# Default command
CMD ["/bin/bash", "-c", "\
cat << 'EOF'\n\
Welcome to the MimIR artifact\n\
\n\
Quick start:\n\
    > cd mim\n\
    > ./build_all.sh                                                  # required only once\n\
    > ./run_benchmarks.py                                             # limimted reproduction\n\
    > ./run_benchmarks.py --full-iters                                # reproduce all numbers\n\
    > ./run_benchmarks.py --remove-llvm --full-iters --warmups --runs # full reproduction (takes 10+ hours)\n\
    >\n\
    > cd lambda-graph\n\
    > lake build                                                      # Lean development of all lemmas and theorems\n\
\n\
EOF\n\
exec /bin/bash"]
