# Use the latest Ubuntu LTS base image
FROM ubuntu:25.10

# Avoid interactive prompts during package installs
ENV DEBIAN_FRONTEND=noninteractive

# create pldi user
RUN useradd -m -u 1000 pldi
USER pldi

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
        bash && \
    rm -rf /var/lib/apt/lists/* && \
    sudo pip install lit psutil && \
    sudo ln -s /usr/bin/FileCheck-20 /usr/local/bin/FileCheck

WORKDIR /home/pldi

# Default command
CMD ["/bin/bash"]
