#!/bin/bash
set -eu

git clone --depth=1 --recursive -b benchmark git@github.com:leissa/mim.git
cp ../bench-mim/*.ll mim/
cd mim
find . -name ".git" -type d -exec rm -rf {} +
rm -f .gitmodules
cd ..

git clone --depth=1 git@gitlab.gwdg.de:j.griebler/lambda-graph.git
cd lambda-graph
find . -name ".git" -type d -exec rm -rf {} +
cd ..
