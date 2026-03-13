# Use the latest Ubuntu LTS base image
FROM ubuntu:25.10

# Avoid interactive prompts during package installs
ENV DEBIAN_FRONTEND=noninteractive

# Update packages and install basic utilities
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        wget \
        git \
        neovim \
        gcc \
        g++ \
        g++-14 \
        llvm-20-tools \
        clang-20 \
        graphviz \
        doxygen \
        texlive \
        python3-pandas \
        python3-psutil \
        bash && \
    rm -rf /var/lib/apt/lists/* && \
    sudo pip install lit psutil && \
    sudo ln -s /usr/bin/FileCheck-20 /usr/local/bin/FileCheck

# create pldi user
RUN useradd -m -u 1000 pldi
USER pldi
WORKDIR /home/pldi

# install Lean
RUN curl https://elan.lean-lang.org/elan-init.sh -sSf | sh -s -- -y

ENV PATH="/home/pldi/.elan/bin:${PATH}"

RUN elan default stable
RUN lean --version && lake --version

# Default command
CMD ["/bin/bash"]
