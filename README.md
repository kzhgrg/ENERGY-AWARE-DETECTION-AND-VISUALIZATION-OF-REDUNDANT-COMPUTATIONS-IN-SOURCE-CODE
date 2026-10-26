# A Static Analysis Framework for Energy-Aware Detection and Visualization of Redundant Computations in Source Code

## Run on macOS
```bash
cd compiler_framework_complete
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

## Run on Windows
```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

## Tests
```bash
python -m unittest discover -s tests -v
```

## Features
- C AST parsing with pycparser.
- Constant folding for supported signed 32-bit integer literal arithmetic.
- Conservative local common subexpression elimination.
- Backward liveness-based removal of unused pure local definitions.
- Power-of-two strength reduction for unsigned-int variables.
- Original vs optimized source, per-line findings, relative static weighted operation cost, reduction percentage, and operation counts.
- Expression DAG, before/after bar visualization, `.c` file input, JSON export, example programs.
- Unsupported blocks are preserved without transformations.

## IMPORTANT LIMITATIONS
- Educational research prototype for **restricted straight-line C functions**. Not a general C optimizer.
- Input must be parseable C without preprocessor directives such as `#include` or `#define`.
- Supported optimized blocks use local `int` / `unsigned int` declarations, simple assignments, pure arithmetic expressions, and returns.
- Blocks with loops, branches, pointers, arrays, calls, or other complex constructs are left unchanged.
- Cost score is an **illustrative static weighted-operation count**, not measured energy, runtime operations, or joules. It ignores control-flow execution frequencies.
- DAG is a structural expression visualization; it does not represent a CFG or guarantee value equivalence across mutations.
- Compiler semantic preservation is not formally verified; review and test output for every transformed program before making correctness claims.
- Run Flask locally only. Do not enable debug mode on a publicly accessible host.

## For a research paper
1. Expand test suite with generated inputs and compare compiled outputs of original vs optimized programs.
2. Add explicit CFG/dataflow analysis for branch/loop optimization, or state these are unsupported.
3. Calibrate operation weights or compare with real measured energy using appropriate hardware tools.
4. Run benchmark programs and compare against compiler optimization baselines.
5. Document limitations and report cases with no optimization benefit.

## Enhanced pass and evaluation notes
- Backward liveness now eliminates dead stores, including overwritten initializers, while retaining required declarations.
- Common-subexpression reuse invalidates cached expressions when dependencies or result variables are overwritten.
- Functions with parameters or global declarations and expressions with potentially uninitialized variables are skipped conservatively.
- The expression graph shows occurrences of operations rather than incorrectly merging identical textual expressions across variable mutations.
- The cost-model metadata is included in the exported JSON report. Scores are static proxies, **not energy measurements**.
- Run `python benchmarks/run_benchmarks.py` to generate `benchmarks/results.csv` for six illustrative programs. These are smoke tests, not publication-quality benchmarks.
- Run `python -m unittest discover -s tests -v` for the expanded regression suite.

### Remaining research limitations
No general control-flow graph or inter-block data-flow solver; no reliable pointer/alias analysis; no side-effect-aware optimization of function calls; no calibration to actual hardware energy; no dynamic loop frequency model. The DAG is an expression-occurrence visualization, not a full SSA/value-numbering graph. For research claims, verify generated code with Clang/GCC and compare observable behavior across test cases.


## Control-flow analysis and branch optimization (new)
- `controlflow.py` builds statement-level CFGs for `if/else`, `while`, `do/while`, `for`, `break`, `continue`, `return`, and approximate `switch` dispatch. It calculates reachability and dominators. `goto` edges are deliberately unresolved; switch fallthrough is approximate. This is **not** full interprocedural data-flow or SSA analysis.
- `branch_pass.py` removes constant-condition `if` branches and `while(0)` loops where the condition has no side effects. It preserves `for`, `do/while`, variable-dependent branches and loops; no general loop-invariant motion, unrolling, or cross-block optimization is claimed.
- The UI displays a control-flow graph and JSON export includes `cfg` and `optimized_cfg`.

## Optional *actual* hardware energy observations (new)
`measure_energy.py` is a local CLI for **trusted, already compiled** benchmarks, never a web endpoint. Energy measurements cannot be performed remotely on your Mac by this project author.

**macOS (Apple Silicon)**: Open a terminal, authorize the system tool with `sudo -v`, then run a sufficiently long workload:

```bash
sudo -v
python measure_energy.py --timeout 40 --interval-ms 100 --output original_energy.json -- ./original_benchmark
python measure_energy.py --timeout 40 --interval-ms 100 --output optimized_energy.json -- ./optimized_benchmark
```

Uses `powermetrics --samplers cpu_power`; reports **approximate CPU energy in joules** calculated from sampled CPU power × elapsed time. This is *system-level* CPU power, not per-process energy. It needs permission, hardware support, enough samples, and a long workload. If no samples are available, the tool reports an error rather than fabricating a result.

**Linux with accessible Intel RAPL**: The same command reads `energy_uj` and returns CPU package energy during the workload interval. Other processes contribute to measured energy.

For meaningful comparisons, use the same input, repeat each test 10+ times, interleave baseline and optimized runs, minimize background activity, and report medians/variance. Compare identical compiler flags and verify program output. Measurements are not currently integrated into the Flask dashboard and **no real energy values are included in the distribution**.

**Limitations:** Hardware-specific, CPU/system-level only; not isolated process joules. macOS sampling is approximate. The static cost proxy is still uncalibrated. This package does not implement general loop optimizations or full alias-aware, interprocedural control-flow analysis.


## Loop analysis and dashboard energy measurement (new)
- Constant-folding is now applied to simple arithmetic assignments inside while/for/do-while bodies, even when the loop count is unknown.
- Provably false `for(;0;)` loops are eliminated when there is no initializer; zero-trip `while(0)` and constant branches remain supported.
- Variable-dependent loops are preserved; general loop-invariant code motion, induction-variable substitution and unrolling are **not** implemented because their correctness requires alias/overflow/termination proofs.
- The dashboard's **Measure bundled benchmarks** button compiles two fixed C programs and samples real machine energy using macOS `powermetrics` or Linux Intel RAPL. This does **not** run pasted source code.
- On macOS: open a terminal, run `sudo -v`, then start Flask from that same terminal and click the button promptly. If no powermetrics CPU Power samples are available, an explicit error appears.
- Measurements are system/package energy during the experiment, not isolated per-process energy. Benchmark programs are illustrative and should be repeated/validated before publication.
- Browser-side measurement requires a local, trusted Flask session. Never expose this development server publicly.


## Advanced loop transformations (restricted subset)

`advanced_loops.py` adds three conservative transformations for canonical
`for (unsigned int i=0; i<N; i++)` loops with simple, side-effect-free
unsigned arithmetic assignments and no nested control flow:

- **Loop unrolling:** fully expands fixed trip counts 1–8, preserving the
  scoped induction variable and its per-iteration increments.
- **Loop-invariant code motion:** hoists one multiplication of unchanged
  unsigned local variables into a fresh temporary when the loop has a
  nonzero constant trip count.
- **Induction-variable optimization:** replaces a single `i * k` expression
  in an unsigned `+=` accumulator with an incrementally maintained temporary.

Other loops remain unchanged. This is **not** general-purpose alias analysis,
inter-block liveness, loop vectorization, or universal loop optimization.
The static cost graph counts AST operations, not executed iterations; unrolling
may increase the static count even when runtime improves. Use compiled
behavioral tests and real hardware measurements to evaluate performance.

Run the expanded suite with `python -m unittest discover -s tests -v`.

### Graph layout update (October 2026)
Both CFG and expression DAG now use hierarchical SVG layout with directional arrowheads, readable full-width statement nodes, branch-edge labels, and dashed orange loop-back edges. Graphs scroll when large; hovering nodes shows complete labels. The renderer does not change compiler analysis or energy measurement logic.
