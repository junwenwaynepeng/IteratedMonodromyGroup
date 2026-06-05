# Iterated Monodromy Groups and the Spider Algorithm

This repository contains experimental code and notes for computing **iterated monodromy groups** associated with post-critically finite maps in arithmetic and complex dynamics.

The main goal is to develop a combinatorial and algorithmic approach to automate part of the **spider algorithm**. In particular, the project studies how path lifting, finite automata, and graph-theoretic structures can be used to describe the monodromy action on the tree of iterated preimages.

## Project Information

**Project Name:**
算術動態系統內的問題 - Tits代替理論與相關的伽洛瓦群
*Problems in arithmetic dynamics - Tits alternative and relative Galois group*

**Project Number:**
113-2115-M-008-012-MY3

**Project Period:**
2025-2027

**Report Period:**
June 1, 2025 - May 31, 2026

## Abstract

This project studies problems in arithmetic dynamics, especially the Tits alternative, arboreal and relative Galois groups, and iterated monodromy groups of post-critically finite maps. During this period, we developed a combinatorial approach to automate the spider algorithm. By using path lifting and finite automata, we introduced the web graph and Lucas paths as tools for choosing suitable path systems. Preliminary results suggest that certain local graph conditions can help construct good spiders and compute iterated monodromy actions effectively.

## 中文摘要

本計畫研究算術動態系統中的問題，特別是 Tits 代替理論、樹狀與相對伽洛瓦群，以及後臨界有限映射的迭代單值群。本年度主要發展一套組合方法來自動化 spider algorithm。透過路徑提升與有限自動機，我們引入 web graph 與 Lucas paths 作為選取合適路徑系統的工具。初步結果顯示，某些局部圖論條件可用來建構 good spiders，並有效計算迭代單值群的作用。

## Keywords

Arithmetic dynamics; Tits alternative; arboreal Galois representations; relative Galois groups; post-critically finite maps; iterated monodromy groups; spider algorithm; finite automata.

## 中文關鍵詞

算術動態系統；Tits 代替理論；樹狀伽洛瓦表示；相對伽洛瓦群；後臨界有限映射；迭代單值群；spider algorithm；有限自動機。

## Mathematical Background

Let \( f \) be a rational map. The iterated preimages of a base point form a rooted tree. The fundamental group of the punctured sphere acts on this tree by path lifting. For a post-critically finite map, this action gives the **iterated monodromy group**.

The spider algorithm gives a way to choose paths from a base point to the post-critical set. These paths determine generators of the fundamental group and allow us to compute recursive relations of the form

$$\texttt{q.x = y.p}$$

where:

* `q` and `p` are states of an automaton,
* `x` and `y` are letters in the alphabet,
* the relation describes how a generator acts on the first level of the preimage tree.

## Main Features

This notebook includes experimental code for:

* defining finite automata;
* computing monodromy generators;
* tracking inverse branches along paths;
* constructing graph models from lifted spider paths;
* searching for good spiders;
* converting graph data into automaton relations.

## Main Objects

### Automaton

An automaton over an alphabet \( X \) is a triple

$$
\langle Q, \lambda, \pi \rangle,
$$

where:

* \( Q \) is the set of states;
* \( \lambda: Q \times X \to X \) is the output function;
* \( \pi: Q \times X \to Q \) is the transition function.

The automaton is finite if \( Q \) is finite.

### Web Graph

The **web graph** is constructed from inverse images of spider legs. It records the combinatorial information needed to understand how lifted paths move among preimages and post-critical points.

### Lucas Paths / Good Spiders

A collection of paths is called a system of **Lucas paths**, or a **good spider**, if the lifted monodromy loops can be represented using a finite set of standard generators. This condition is designed to make the iterated monodromy action computable by a finite automaton.

## Requirements

The notebook uses SageMath-style syntax and depends on packages such as:

```text
SageMath
matplotlib
networkx
numpy
```

It is recommended to run the notebook with a SageMath Jupyter kernel.

## Files

```text
IteratedMonodromyGroup.ipynb
```

This notebook contains the main experimental implementation.

## Current Status

This is a research prototype. The code is intended for experimentation with post-critically finite maps, spider graphs, and iterated monodromy groups. Some parts are still under development, especially the general search procedure for good spiders and the conversion from web graph data to automaton relations.

## Future Work

Planned next steps include:

* completing the graph-theoretic criterion for good spiders;
* improving the implementation of the web graph construction;
* testing the method on more degree-two and degree-three PCF maps;
* comparing the computed automata with known iterated monodromy groups;
* preparing the results for a research article.

## Author

Wayne Peng
Department of Applied Mathematics
National University of Kaohsiung
