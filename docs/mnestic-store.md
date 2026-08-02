# Mnestic Datalog Query Stores

> Status: v1 design decisions. Read-only querying only. Scoped
> deliberately to **mnestic** (CozoDB, `rocksdb` backend) — the filename
> and type key are specific on purpose; a neutral "datalog store"
> abstraction is a later generalization, not a v1 commitment.
> Implementation not yet started.
>
> **What v1 covers.** A new `RuleSetStore` type that exposes an
> externally-populated mnestic term database for *querying* from inside
> `constraint`, via a `query/1` operator that compiles a conjunctive goal
> region to CozoScript, runs it, and enumerates result rows as solution
> branches. **Writing/loading is entirely out of scope** — the database is
> populated offline in a separate process; `constraint` only reads it.
> The worked example throughout is the treesitter → CST nested-function
> query proven standalone in prior work; the goal of the first
> implementation block is to run that same query from *inside* constraint.

## What this doc covers

The architecture of a **mnestic query store**: how an externally-built
CozoDB term database is attached to a `constraint` program as a store,
how the store's relations become queryable Prolog goals, and how a
conjunctive query region is compiled to CozoScript and run with results
threaded back as ordinary Prolog solutions.

Clause dispatch and the meta-interpreter kernel are covered in
[`reduce-goal.md`](reduce-goal.md); rule-set scoping and the `chain`
composition model in [`rule-scoping.md`](rule-scoping.md). This doc reuses
both — the mnestic store is a `RuleSetStore` in its own right — and does
not restate them.

## Framing

`constraint`'s existing stores answer "what clauses define this
predicate?" from Prolog files ([`FileRuleSetStore`](../src/constraint/store/store.py)).
A **mnestic query store** is a different kind of source: it does not
contribute `rule/2` clauses to ordinary resolution at all. Instead it
attaches a **term database** — a set of stored relations populated
offline — and makes those relations queryable through a dedicated
`query/1` region whose body is compiled to the backend's dialect and
executed there, not walked by the meta-interpreter.

Two motivations drive keeping this separate from ordinary rule dispatch:

- **The backend is the query engine.** A conjunctive query with joins,
  a recursive transitive closure, and a guard is exactly what CozoDB is
  good at. Reducing it one goal at a time Prolog-side and joining in the
  meta-interpreter would discard the entire point of using mnestic. The
  whole region must be shipped as **one** script.
- **Recursion belongs to the backend.** Transitive closure
  (`descendant` over `parent_id`) is a derived, recursive relation. It
  cannot be reduced against stored facts goal-by-goal; it must be handed
  to cozo as a recursive rule. So the store's supporting relations are
  *compiler input*, not interpreter input.

The v1 lock-in to mnestic/CozoScript is intentional and named. The
neutral-representation ambition — a Prolog term language for datalog that
adapters compile to any backend — is explicitly [deferred](#deferred--out-of-scope-for-v1);
v1 builds the one concrete adapter first so the seam is designed against
a real target rather than in the abstract.

## Configuration

A mnestic store is declared alongside file stores in the program config:

```yaml
stores:
  - name: "rules"
    path: "rules.pl"
    type: "file"
  - name: "source"
    path: "source.db"
    type: "mnestic"
    support: "source_query_support.pl"
```

Fields specific to the mnestic store:

- **`path`** — the CozoDB database directory/file to open. Read-only
  (see [Lifecycle](#store-lifecycle)).
- **`type`** — `"mnestic"`. The backend is `rocksdb` for v1. If a second
  backend ever appears, the recommended encoding is a separate
  `backend:` key (`type: "mnestic"`, `backend: "rocksdb"`) rather than a
  `mnestic-rocksdb` compound type key, so the store type and its storage
  engine stay orthogonal. v1 may assume `rocksdb` and need not read a
  `backend:` key yet.
- **`support`** — path to a Prolog file of user-authored **query support
  rules** (the derived relations a query needs — `descendant`,
  `nested_fn`, …). See [Generated and supporting predicates](#generated-and-supporting-predicates).

## Generated and supporting predicates

Querying a mnestic store needs two kinds of predicate, and **neither is a
`rule/2` clause**. They live in a namespace distinct from ordinary
resolution so they never collide with `user:rule/2` dispatch or with the
kernel's goal reduction. They exist only to (i) let a `query/1` region
name relations and derived predicates naturally, and (ii) feed the
compiler.

### Schema-derived base predicates

At store open, the adapter **discovers the store's schema** from the live
database — the stored relations, their columns, and column types
([full descriptor](#schema-discovery), load-bearing for the compiler).
From that descriptor it generates one **base predicate per stored
relation**, positional over the relation's columns in schema order. For
the CST example the discovered `*node` relation yields:

```
node(Id, Kind, ParentId, StartByte, EndByte,
     StartRow, StartCol, EndRow, EndCol, IsNamed, Text)
```

These generated predicates are the compiler's notion of a **base
relation**: a goal whose functor names a discovered relation compiles to
a stored-relation match against mnestic.

### User support rules (`query_rule/2`)

The user writes derived relations as **ordinary-looking Prolog** in the
`support` file:

```prolog
descendant(A, D) :- node(D, _, A, _,_,_,_,_,_,_,_).
descendant(A, D) :- node(M, _, A, _,_,_,_,_,_,_,_), descendant(M, D).

nested_fn(O, I) :-
    node(O, function_definition, _, _,_,_,_,_,_,_,_),
    node(I, function_definition, _, _,_,_,_,_,_,_,_),
    descendant(O, I),
    O \= I.
```

On load these are **wrapped as `query_rule(Head, Body)` facts**, exactly
analogous to how [`FileRuleSetStore`](../src/constraint/store/store.py)
wraps ordinary clauses into `rule(Head, Body)` (`_wrap_constraint_clause`)
so the user can author naturally while the interpreter consumes a
uniform term. The distinct functor (`query_rule/2` vs `rule/2`) is what
keeps these out of ordinary dispatch.

`query_rule/2` clauses are **inert data for the compiler**. They are
never executed Prolog-side and never enter `reduce_goal`'s general
`rule/2` path. The compiler reads them to lift derived relations into
cozo rules; nothing else consults them.

### Merge

The mnestic store presents the **schema-derived base predicates merged
with the loaded `query_rule/2` support facts** as its content. A new
`RuleSetStore` subclass owns this: on open it discovers the schema,
generates the base predicates, loads and wraps the `support` file, and
exposes the merged set. Whether the generated base predicates are
materialized to a temp `.pl` and loaded through the existing
`FileRuleSetStore` machinery, or injected in memory, is an implementation
choice; the store-level contract is that the merged content is what the
store owns. Content-hashing and `chain` composition apply unchanged — a
mnestic store composes into `@top` like any other member, subject to the
same immutability contract (same database + same support file ⇒ same
generated content ⇒ same hash).

## The `query/1` operator

`query/1` is a **new `reduce_goal` clause** in the kernel. A goal

```prolog
query(( node(O, function_definition, _, _,_,_,_,_,_,_,_),
        descendant(O, I),
        O \= I,
        node(_, identifier, O, _,_,_,_,_,_,_, Name) ))
```

demarcates a **compile-and-ship region**: the entire conjunction inside
`query/1` is compiled to one CozoScript script, run against the store's
handle, and its result rows are enumerated back as solutions. The `query`
wrapper (rather than bare `?-`-style goals) is what tells the kernel
"this region is answered by the backend, not by resolution."

Reduction is **row-per-branch**, so a query composes with the rest of the
resolvent like ordinary Prolog:

- each returned row binds the region's [output variables](#projection)
  and becomes one solution branch;
- multiple rows become multiple branches, spliced DFS in the usual way
  (see [`reduce-goal.md` §Kernel mechanics](reduce-goal.md));
- backtracking into a `query/1` enumerates the next row.

From the author's side, `query((...))` reads like a conjunction of goals
that happens to be answered all at once. The point is that it *feels*
Prolog-native while the backend does the relational work.

## The compiler

Compilation from the `query/1` region to CozoScript is **Prolog-side and
adapter-specific**. It works over the **positional** internal terms (the
schema-derived base predicates and `query_rule/2` bodies), which keeps
the compiler uniform; the [sugar surface](#user-facing-sugar) is expanded
away before the compiler sees anything.

### Conjunct classification (by origin, no tagging)

Walking the region's conjunction, each conjunct is classified by
**where its functor comes from** — there is no tagging in the support
file:

- functor names a **discovered relation** → **base match** (stored
  relation in cozo);
- functor is a **`query_rule/2` head** → **derived relation** (lift its
  clauses into a cozo recursive/derived rule);
- functor is a **known builtin** → **guard**.

Classification is purely by origin: the schema descriptor and the set of
`query_rule/2` heads are the two registries; everything else is a builtin
or an error.

### Builtins and guards (v1 minimal set)

v1 supports exactly:

- `=/2` — unification / equality;
- `\=/2` — inequality (the demo's `O \= I` guard);
- **column-constant match** — a constant in a base-relation argument
  position (the demo's `kind = function_definition`, expressed as the
  constant `function_definition` in `node/11`'s second argument).

Any other builtin in a `query/1` region is a **hard compile error**. v1
does **not** fall back to Prolog-side post-filtering. Failing fast keeps
the compile seam honest — an unsupported construct surfaces immediately
rather than silently splitting evaluation across two engines — and is the
conservative choice for not painting the design into a corner. The guard
set widens deliberately, guard by guard, as real queries need it.

### Projection (correct from the start)

The columns the compiled query returns are the region's **output
variables**: unbound variables appearing inside the `query/1` region that
**also occur outside it** — in the surrounding resolvent or the original
goal. Variables local to the region (appearing only inside `query/1`) are
existential and are **not** returned. This is genuine projection, not
"return every region variable," and it is in scope for v1 — over-
returning is not an acceptable v0 shortcut here because it would leak
existential variables into the solution bindings.

### Prolog-side compiler placement

The Prolog half of the compiler lives as **ordinary Prolog in a sibling
file to `meta.pl`** (the meta-interpreter's own `.pl` source), loaded
alongside it. Concretely it is consulted through the same
`_ensure_*_loaded` pattern `meta.py` already uses to load `meta.pl` and
the foreign-callout module (`importlib.resources` + a process-level
`_consulted` guard). The `query/1` `reduce_goal` clause and the
compiler predicates it calls are thus part of the kernel's loaded Prolog
program. The Python half — schema discovery, `run_script`, row
marshalling — lives in the mnestic adapter (below).

## Prolog / Python split

Mirrors the split in [`reduce-goal.md`](reduce-goal.md):

- The **Prolog kernel** owns: the `query/1` `reduce_goal` clause, conjunct
  classification, compilation of the region to a CozoScript string, and
  enumeration of returned rows into solution branches.
- **Python** owns the **mnestic adapter**: opening the database, schema
  discovery, executing the compiled script via
  `run_script(script, params, immutable)` against `mnestic.CozoDbPy`, and
  marshalling result rows back to the kernel.

The kernel reaches the adapter through the existing Janus foreign-callout
path (`foreign(Fn, In, Out)` → `py_call`), the same mechanism the general
store oracle uses. Calling out is **not** a suspension: the backend
answers immediately, so a `query/1` reduces inline.

### The `run_script` mutability flag

The adapter executes via `run_script(script, params, immutable)`. In v1
every `query/1` is a **read** (`immutable` → read-only), consistent with
writing being out of scope. The mutability flag is nonetheless the more
durable seam than the database open-mode: it is the point at which
read-query vs future mutating-load is discriminated per call. Recording
it now means the eventual load path slots in behind the same method
rather than forcing a new one.

## Schema discovery

Schema discovery returns a **full descriptor** — relations, their
columns, and column types — not merely relation names and arities. It is
**load-bearing**, not a convenience: the compiler is written per adapter
and is allowed to use everything the backend offers, and validating a
query region against the real schema (catching a wrong column or a
type mismatch at compile time) depends on having the full descriptor. If
a future backend cannot supply types, that constraint is evaluated when
it arises; mnestic can, so v1 assumes it.

## User-facing sugar

The positional base predicates (`node/11`) are the compiler's target, not
necessarily the surface an author wants to write against — eleven
positional arguments with underscores is noisy and brittle against schema
change. A **param-keyed projection sugar** lets a query name only the
columns it cares about, e.g.:

```prolog
node_match([id-O, kind=function_definition])
```

This is **surface sugar only**. It desugars to the positional
`node/11` form (binding `O`, matching the constant, leaving the rest
anonymous) *before* the compiler runs, so the compiler continues to see
only positional terms. The sugar is generated from the discovered schema
(column names come from the descriptor); its exact shape — the `-` bind /
`=` constant-match convention shown here, or another — is a surface
decision, not a compiler concern.

## Worked example: nested-function query

The reference query end-to-end, carried over from the standalone
treesitter → mnestic CST pipeline proven in prior work. Schema:

```
*node{id => kind, parent_id?, start_byte, end_byte,
      start_row, start_col, end_row, end_col, is_named, text}
```

Support rules (`support` file): `descendant/2` as the transitive closure
over `parent_id`; `nested_fn/2` selecting a `function_definition` node
with a `function_definition` descendant under an `O \= I` guard (as shown
[above](#user-support-rules-query_rule2)).

Query region:

```prolog
query(( nested_fn(O, _),
        node(_, identifier, O, _,_,_,_,_,_,_, Name) ))
```

Outputs `O` (outer function node id) and `Name` (its name, resolved by
joining the direct `identifier` child on `parent_id = O`). Against a file
with a `def outer_function` containing a nested `def inner_function`, the
query returns the single `outer_function` row.

Note: the correct treesitter node kind is **`function_definition`**
(snake_case CST kind), **not** the stdlib `ast` `FunctionDef`. There is no
`name` column in the schema; a function's name is the text of its direct
`identifier` child, recovered by the join above.

The first implementation block's target is exactly this: the query runs
from **inside** `constraint` via `query/1` against the real mnestic
database and returns the same row the standalone pipeline produced.

## Deferred / out of scope for v1

- **Write / load path.** Populating the database from `constraint` is
  entirely out of scope; v1 reads an externally-populated store. When it
  arrives it slots behind the same `run_script(..., immutable)` seam
  (mutating vs read-only), likely as a distinct store-side operation
  rather than a `query/1` region.
- **Neutral query representation.** A backend-independent Prolog term
  language for datalog, with cozo as one compile target behind an
  adapter interface — the real fix for CozoScript lock-in. v1
  deliberately commits to mnestic/CozoScript and builds the concrete
  adapter first; the neutral layer is designed once there are queries
  worth expressing natively.
- **Second backend / the `backend:` key.** Only `rocksdb` mnestic in v1.
  The orthogonal `backend:` encoding is recommended for when a second
  engine appears, not implemented now.
- **Wider builtin / guard set.** Beyond `{=/2, \=/2, column-constant
  match}`; aggregation and negation especially are cozo-specific in their
  semantics and are not portable datalog — deferred until a query needs
  them, and a candidate driver for the neutral representation above.
- **Handle / discovery lifecycle changes.** v1 opens once and memoizes
  the handle, schema descriptor, and generated ruleset for the process
  lifetime (see below). Re-open, invalidation, and live-updating stores
  are expected to change and are out of scope now.
- **AST-conversion / rewrite transforms.** Transforms that rewrite parsed
  terms live *above* the query layer, not in datalog; that boundary is
  designed once querying-out subterms works.
- **Text elision.** The schema's `text` column duplicates source (the
  root node's text is the whole file); eliding it in favor of reslicing
  `start_byte`/`end_byte` is a known optimization, deferred.
- **`(Hash, PI)` oracle keying.** The goal-agnostic keying and Prolog-side
  clause cache described in [`reduce-goal.md`](reduce-goal.md) are
  themselves deferred there; how a mnestic store interacts with them is
  settled when they land.

### Store lifecycle

v1 opens the mnestic database on **first access** — at program start or
just-in-time — and **memoizes** the handle, the schema descriptor, and
the generated + merged ruleset for the process lifetime. There is no
per-query reopen and no per-query rediscovery. The open is **read-only**.
This is expected to change (concurrent writers, live stores); it is
recorded as the v1 simplification, with the `run_script` mutability flag
(not the open-mode) noted as the durable discrimination point.
