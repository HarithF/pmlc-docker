# Artifact Evaluation: SSA without Dominance for Higher-Order Programs

## Quick Reproduction (Recommended)

```sh
docker load < mimir.tar.gz # load the image
docker run -it --name mimir-run mimir # run the container named 'mimir-run'
cd mim
./build_all.sh
./run_benchmarks.py        # generates mim/tex/bench.pdf
cd ../lambda-graph
lake build                  # lean development
```
This produces a reduced version of Fig. 6 in ~1 hour.

## General Information

The artifact consists of two parts:
1. The research compiler IR *MimIR* that we used to create Fig. 6 in the paper.
2. A Lean development *lambda-graph* that verifies all lemmas and theorems in the paper.

## MimIR

The original Fig. 6 in the paper consists of 3 x 3 plots:
Each column benchmarks the implementation of one algorithm in the compiler:
1. free variables computation
2. $\beta$-reduction
3. nesting tree construction
Each row tests a synthetic program whose size is doubled with every tick on the x-axis (for this reason we use a double-log scale):
1. Loop Cascade
2. Acc. Loop Cascade
3. Loop Nest
The y-axis depicts runtime in micro seconds.

Each plot tests two different set implementation that are used to implement the algorithms above:
* [immer](https://sinusoid.es/immer/): mutable and persistent data structures for C++ - value semantics at scale
* an indexed trie: a new data structure presented in the paper

The reviewers, however, asked for more data:
>   - Improvement of the benchmarks:
>       - This should include some justification that the clever data structures used are necessary;
>       - This should include a comparison with standard compilers, e.g. LLVM.

For this reason, we have updated Fig. 6 with the following data:
* a naive `std::set` implementation
* we compile all MimIR examples to LLVM and compare
    * LLVM's dominance analysis against MimIR's free variable computation
    * inlining (both with and without additional optimizations that simulate MimIR's on-the-fly optimizations) against MimIR's $\beta$-reduction.
You can inspect the update like this:
```sh
docker cp mimir-run:/home/ubuntu/mim/tex/bench.pdf .
xdg-open bench.pdf
```
Finally, we added in each plot a guide to better judge the asymptotic behavior of the plots in the double-log scale.

### Building

Inside the docker image:
```sh
cd mim
./build_all.sh
```
This will take around 10 minutes and you only need to do this once.

Our fork of MimIR contains `#ifdef`s for the three different set implementations.
For this reason, the build script will build three sets of binaries:
* `~/mim/release_trie/bin`
* `~/mim/release_immer/bin`
* `~/mim/release_set/bin`

### Benchmarks

Running the full benchmark suite requires 15+ hours on a modern computer.
For this reason, the benchmark script provides a couple of options that drastically reduce the time.
1. Print help:
   ```sh
   ./run_benchmarks.py -h
   ```
2. Fastest option: requires around 1 hour.
    * Less precision.
    * Measurements are only done up to $2^{10}$.
   ```sh
   ./run_benchmarks.py
   ```
3. As above but includes the whole measurement range.
    * Takes around 2 hours.
   ```sh
   ./run_benchmarks.py --iters
   ```
4. As above but all tests are run 9 times.
    * min, max, and median will be computed and plotted
    * Takes **9 times** as long as 3.!
   ```sh
   ./run_benchmarks.py --iters --runs
   ```
5. As above but includes 3 warm up runs before doing the actual measurements.
    * Takes **14 times** as long as 3.!
    ```sh
   ./run_benchmarks.py --iters --runs --warmups
   ```
6. As above but will freshly generate the `*.ll` files.
    * **Adds another ~2 hours**.
    ```sh
   ./run_benchmarks.py --iters --runs --warmups --remove-llvm
   ```
Each run of this script will build with the gathered data a new plot that you can inspect from outside of docker like this:
```sh
docker cp mimir-run:/home/ubuntu/mim/tex/bench.pdf .
xdg-open bench.pdf
```
Note that the colors and style changed compared to the original Fig. 6 in the paper.

### Documentation

The project documentation will also be built that you can inspect like this:
```sh
docker cp mimir-run:/home/ubuntu/mim/release_trie/html ./html
xdg-open html/index.html
```

### Reusability

The build command above also builds the test suites that you can invoke like this from inside docker:
```sh
cd mim/release_trie
make test # unit tests
make lit  # lit test suite
```
You can find the `lit` tests in `mim/lit`.
Feel free to poke around!

## Lambda-Graph

Enter the docker image and verify via:
```
cd lambda-graph
lake build
```
Check out `lambda-graph/README.md` for more information.
