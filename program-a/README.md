# Program A

Program A studies uniform upper bounds for the level indices $I_n$ of a **specified rooted-tree action**. Start from its wreath recursion. Choose a method according to the subgroup or certificate you have.

| Command | Mathematical operation | Output |
| --- | --- | --- |
| [kh](program_a/kh/cover.py) | Form a presentation of the coordinate product using verified relations. Use GAP NEWTC to enumerate a cover for the supplied section tuples. | A certificate with signed transitions, a whole-tree check, and an independent raw replay. The number of representatives gives an upper bound for every $n ≥ 1$. |
| [n](program_a/n/engine.py) | Search for a finite normal cover and witnesses lifting generators into individual coordinates. | A checked bound when the required cover and lifts are found. See [supported-image and strong checks](program_a/n/assembly.py). |
| [index](program_a/kh/index.py) | Compute GAP Index in the coordinate product. Supply selected tuples for K, or explicitly choose the full first-level stabilizer image H. | A GAP program returning the native subgroup index if the computation terminates. |
| [fr](program_a/fr/branch.g) | Construct the FR group on the original states, call BranchingSubgroup(G), then IsBranched(G) on the same group. | A GAP program returning the native FR predicate. |
| [replay](program_a/kh/cover.py) | Replay a saved KH certificate on its input action with both interpreters. | The bound and both verification records, or the stage that failed. |

## Run a small example

Use Python 3.10+ from this directory. The Python search and checkers use the standard library. Install GAP 4.12.1 for KH. Its validated extraction guards read the matching GAP library sources from `/usr/share/gap/lib`; set `PROGRAM_A_GAP_LIB` for another installation. The GAP executable on PATH must use that installation. For the two GAP scripts install the FR package (tested with 2.4.13) and its dependencies. Run Python with assertions enabled.

```sh
python3 -m program_a --help
python3 -m program_a kh examples/root-swap.json examples/root-swap-pool.json > result.json
python3 -m program_a replay examples/root-swap.json result.json
python3 -m program_a n examples/root-swap.json
python3 -m program_a index examples/root-swap.json --full-h > index.g
gap -q -b -T index.g
python3 -m program_a fr examples/grigorchuk.json > branch.g
gap -q -b -T branch.g
python3 -m unittest discover -s tests -v
```

The root-swap action has one generator of order two and trivial sections. Its first-level stabilizer is trivial, and the coordinate product has order four. The example KH pool therefore needs just the relation `[1,1]` and an empty tuple list. The expected KH bound is **4**. The FR example uses the four-state recursion of the first Grigorchuk group and returns **true**.

## Inputs and results

- An [action packet](examples/root-swap.json) carries a map identifier, a table identifier and a model. Each root row is a zero-based permutation. Each section is zero for the identity or a signed, one-based original state. Words act from left to right.
- A [KH pool](examples/root-swap-pool.json) supplies `verified_relators_basis` and `tuple_generators`. Each tuple records a root-fixing parent word and its sections in coordinate order. The command checks them against the action. An optional `basis_words` / `original_generator_words` pair changes the presentation basis. Without the pair the original states form the basis.
- Use `index ACTION --pool POOL` for a selected tuple subgroup. Even an empty list selects that subgroup. Use `--full-h` to construct H from the first-level stabilizer.
- Native GAP answers describe the requested subgroup or predicate. A KH cover size can exceed the exact index. Resource limits and unfinished searches leave the mathematical question open.

## Source layout

`program_a/kh/` contains the presentation-to-certificate workflow, NEWTC guards, the native index adapter and independent replay. `program_a/n/` contains normal subgroup selection, insertion search, witness assembly and verification. `program_a/fr/` contains the native FR diagnostic. `program_a/shared/` holds action arithmetic, tuple operations and reusable proof routines. The [command dispatcher](program_a/__main__.py) selects the method.

This is the single-action research edition derived from the KH6 release (scientific specification SHA-256 `e77aa6c22c5009eba2b47fbd9316b65254476979059ec726746f99104790dbe2`). The laboratory batch scheduler, storage ledger, dashboard, saved case pools and run traces are maintained separately. For reproducibility, record the action, pool, command, GAP/FR versions and Git commit alongside each result.
