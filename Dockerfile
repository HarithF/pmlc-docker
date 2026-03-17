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
        wget \
        cmake \
        git \
        neovim \
        gcc-15 \
        g++-15 \
        llvm-21 \
        llvm-21-tools \
        clang-21 \
        texlive \
        texlive-latex-extra \
        graphviz \
        ghostscript \
        python3-pandas \
        python3-psutil \
        python3-pip \
        bash && \
    rm -rf /var/lib/apt/lists/* && \
    pip3 install --break-system-packages lit             && \
    ln -s /usr/bin/gcc-15       /usr/local/bin/gcc       && \
    ln -s /usr/bin/g++-15       /usr/local/bin/g++       && \
    ln -s /usr/bin/clang-21     /usr/local/bin/clang     && \
    ln -s /usr/bin/clang++-21   /usr/local/bin/clang++   && \
    ln -s /usr/bin/FileCheck-21 /usr/local/bin/FileCheck && \
    ln -s /usr/bin/opt-21       /usr/local/bin/opt

RUN cd /usr/local/ && wget https://www.doxygen.nl/files/doxygen-1.13.2.linux.bin.tar.gz -O doxygen.tar.gz && \
    tar xf doxygen.tar.gz && \
    ln -s /usr/local/doxygen-1.13.2/bin/doxygen        /usr/local/bin/doxygen        && \
    ln -s /usr/local/doxygen-1.13.2/bin/doxyindexer    /usr/local/bin/doxyindexer    && \
    ln -s /usr/local/doxygen-1.13.2/bin/doxysearch.cgi /usr/local/bin/doxysearch.cgi && \
    ln -s /usr/local/doxygen-1.13.2/bin/doxywizard     /usr/local/bin/doxywizard

USER ubuntu
WORKDIR /home/ubuntu

# install Lean
RUN curl https://elan.lean-lang.org/elan-init.sh -sSf | sh -s -- -y
ENV PATH="/home/ubuntu/.elan/bin:${PATH}"
RUN elan default stable
RUN lean --version && lake --version

# prepare repos
COPY --chown=ubuntu:ubuntu mim /home/ubuntu/mim/
COPY --chown=ubuntu:ubuntu lambda-graph/ /home/ubuntu/lambda-graph/

# Default command
CMD ["/bin/bash", "-c", "\
cat << 'EOF'\n\
Welcome to the MimIR artifact\n\
\n\
Quick start:\n\
    cd mim\n\
    ./build_all.sh                                                  # required only once\n\
    ./run_benchmarks.py                                             # limited reproduction\n\
    ./run_benchmarks.py --full-iters                                # reproduce all numbers\n\
    ./run_benchmarks.py --remove-llvm --full-iters --warmups --runs # full reproduction (takes 10+ hours)\n\
    \n\
    cd lambda-graph\n\
    lake build                                                      # Lean development of all lemmas and theorems\n\
\n\
EOF\n\
exec /bin/bash"]
