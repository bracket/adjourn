# Graph coloring

Colors the vertices of a 4-cycle (`a - b - c - d - a`) with red, green and
blue so that no two adjacent vertices share a color. With `a` fixed to red,
there are six colorings.

The search is ordinary Prolog backtracking, but it runs one step at a time
from the command line. Each `adjourn resume` is a new process: it reads the
saved state, continues the search until something reportable happens, writes
the state back, and exits.

The rules are in [`coloring.pl`](coloring.pl). Each valid coloring hits
`yield(found)`, which suspends the search before the coloring is reported.

## Walkthrough

From this directory, set up a project config and register the rules:

```bash
adjourn config init
adjourn rules add coloring.pl
```

Create a state for the goal `coloring(A, B, C, D)`:

```bash
adjourn init "coloring(A, B, C, D)" state.json
```

Then resume it, in place, as many times as you like:

```console
$ adjourn resume state.json state.json
status: suspended — label: "found"
ruleset_hash: d9402234e3f2
resume_hash:  d9402234e3f2
goal: coloring(A, B, C, D)
```

Later output is trimmed to the status line:

```console
$ adjourn resume state.json state.json
status: solution — bindings: A=red, B=green, C=red, D=green
$ adjourn resume state.json state.json
status: suspended — label: "found"
$ adjourn resume state.json state.json
status: solution — bindings: A=red, B=green, C=red, D=blue
```

Each coloring takes two resumes: the first stops at the `yield`, the next
reports the coloring as a solution with the goal's variables bound. Resuming
past a solution backtracks into the remaining choices for the next coloring.
After the sixth coloring, the search is exhausted:

```console
$ adjourn resume state.json state.json
status: done
```

You can stop at any point and pick up later: everything the search needs is
in `state.json`. `adjourn state show state.json` prints the current status
without advancing; add `-v` to see the pending branches, the choices the
search has yet to explore.
