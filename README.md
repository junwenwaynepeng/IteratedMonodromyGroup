# Iterated Monodromy Group & Automata for Rational Maps

> Computational tools for tracking inverse branches of rational maps, computing monodromy permutations around critical values, and constructing associated automata.

---

## Overview

This project provides a computational framework for **complex and arithmetic dynamics**, focused on:

- Tracking **inverse branches** of a rational function along controlled paths
- Computing **monodromy permutations** associated to critical values
- Constructing **finite automata** encoding symbolic dynamics and monodromy relations
- Visualizing inverse-branch continuation and branch interactions

The code is designed for **post-critically finite (PCF)** and general rational maps, with special handling of **∞ via conjugation** when the map is polynomial.

---

## Mathematical Background

Let  
$$
f : \mathbb{P}^1(\mathbb{C}) \to \mathbb{P}^1(\mathbb{C})
$$
be a rational map.

Key objects computed in this project:

- **Critical points** \( C_f \)
- **Critical values** \( P_f = f(C_f) \), closed under iteration
- **Inverse branches** continued along homotopy-controlled paths
- **Monodromy permutations** acting on preimages of a base point
- **Automata** encoding symbolic transition/output relations

This framework supports experimentation related to:

- Iterated monodromy groups
- Thurston theory
- Arboreal representations
- Symbolic dynamics of rational maps

---

## Features

- Inverse branch continuation via Newton refinement  
- Path deformation avoiding post-critical values  
- Greedy matching of inverse branches between steps  
- Automatic handling of infinity via conjugation \( x \mapsto 1/f(1/x) \)  
- Permutation extraction from circular ordering of preimages  
- Finite automaton construction and validation  
- Visualization of inverse branches and automaton graphs  

---

## Requirements

- **SageMath** (tested with Sage ≥ 10)
- Python packages:
  - `networkx`
  - `matplotlib`
  - `numpy`

---

## Quick Start

### Define the map and base point

```python
x = var('x')
f = -4*x^3 + 6*x^2 - 1/2
base_point = 1 + I
generators, label2index, crit_points, crit_values = permutation_form(
    f,
    base_point,
    steps=10
)
```
Returns:
- generators: dictionary mapping critical values (and ∞) to permutations
- label2index: stable labeling of inverse branches
- crit_points: critical points of f
- crit_values: post-critical set, closed under iteration

```python
figs = preimage_path_plots(
    f,
    base_point,
    steps=40,
    include_infty=True
)

figs['infty'].show()
```
Each plot shows:
- Colored inverse branches
- The continuation path
- Critical values (optional)

```python
automaton = Automaton()
string_list = [
    'a.0=1.b',
    'a.1=0.c',
    'b.0=1.c',
    'b.1=0.a',
    'c.0=0.c',
    'c.1=1.c'
]
automaton.from_string_list(string_list)

print(automaton.is_valid())
print(automaton.is_irreducible())
automaton.graph()
```
The automaton supports:
- Validity checks
- Invertibility checks
- Irreducibility testing
- Visualization via `networkx`

## Todo list:
[ ] Draw automata associated with a PDF
[ ] Define Wreath Product class
[ ] Compute the generators of the iterated monodromy groups
