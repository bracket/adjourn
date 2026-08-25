# Mnestic Datalog Query Stores

> Status: v1 design decisions. Read-only querying only. Scoped
> deliberately to **mnestic** (CozoDB, `rocksdb` backend) — the filename
> and type key are specific on purpose; a neutral "datalog store"
> abstraction is a later generalization, not a v1 commitment.
> Support-file loading has landed (PR #49); the `query/3` compiler is the
> next implementation block and is specified here.
>
> **What v1 covers.** A new `RuleSetStore` type that exposes an
> externally-populated mnestic term database for *querying* from inside
> `constraint`, via a `query/3` operator (findall-shaped:
> `query(Template, Query, Bag)`) that compiles a conjunctive query to
> CozoScript, runs it, and collects result rows into `Bag`.
> **Writing/loading is entirely out of scope** — the database is
> populated offline in a separate process; `constraint` only reads it.
> The worked example throughout is the treesitter → CST nested-function
> query proven standalone in prior work; the goal of the first
> implementation block is to run that same query from *inside* constraint.

## What this doc covers

The architecture of a **mnestic query store**: how an externally-built
CozoDB term database is attached to a `constraint` program as a store,
how the store's relations become queryable Prolog goals, and how a
conjunctive query is compiled to CozoScript and run with result rows
collected into a bag (findall-shaped), not threaded into the resolvent.

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
`query/3` goal whose `Query` argument is compiled to the backend's
dialect and executed there, not walked by the meta-interpreter.

Two motivations drive keeping this separate from ordinary rule dispatch:

- **The backend is the query engine.** A conjunctive query with joins,
  a recursive transitive closure, and a guard is exactly what CozoDB is
  good at. Reducing it one goal at a time Prolog-side and joining in the
  meta-interpreter would discard the entire point of using mnestic. The
  whole query must be shipped as **one** script.
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
kernel's goal reduction. They exist only to (i) let a `query/3` query
name relations and derived predicates naturally, and (ii) feed the
compiler.

### Schema-derived base predicates

At store open, the adapter **discovers the store's schema** from the live
database — the stored relations, their columns, and column types
([full descriptor](#schema-discovery), load-bearing for the compiler).
From that descriptor it knows one **base relation per stored relation**,
named by the relation's functor with its set of valid column keys. For the
CST example the discovered `*node` relation has columns:

```
node{id, kind, parent_id, start_byte, end_byte,
     start_row, start_col, end_row, end_col, is_named, text}
```

A base relation is addressed through the **keyed surface** — a goal
`node(id: X, kind: 'function_definition')` names only the columns it
constrains and compiles to a stored-relation match against mnestic. This
discovery is what lets Python (not Prolog) classify a query goal as a base
match: its functor names a discovered relation and its keys are valid
columns.

### User support rules (`query_rule/2`)

The user writes derived relations as **ordinary-looking Prolog** in the
`support` file:

```prolog
descendant(Anc, Desc) :- node(id: Desc, parent_id: Anc).
descendant(Anc, Desc) :- descendant(Anc, Mid), node(id: Desc, parent_id: Mid).

nested_fn(O, I) :-
    node(id: O, kind: 'function_definition'),
    node(id: I, kind: 'function_definition'),
    descendant(O, I),
    O \= I.
```

Support-rule bodies use the **same keyed base surface** as `query/3`
queries — one vocabulary everywhere.

On load these are **wrapped as `query_rule(Head, Body)` facts**, exactly
analogous to how [`FileRuleSetStore`](../src/constraint/store/store.py)
wraps ordinary clauses into `rule(Head, Body)` (`_wrap_constraint_clause`)
so the user can author naturally while the interpreter consumes a
uniform term. The distinct functor (`query_rule/2` vs `rule/2`) is what
keeps these out of ordinary dispatch.

`query_rule/2` clauses are **inert data for the compiler**. They are
never executed Prolog-side and never enter `reduce_goal`'s general
`rule/2` path. The Prolog compiler reads them only to collect the transitive closure of
referenced derived relations into the emitted term; Python lifts them to
cozo `:=` rules. Nothing else consults them.

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

## The `query/3` operator

`query/3` is a **new `reduce_goal` clause** in the kernel. It is
**findall-shaped**:

```prolog
query(Template, Query, Bag)
```

- **`Template`** — a term `Functor(Col1, Col2, ...)` where `Functor` is an
  arbitrary name chosen by the author and each argument names a
  **projection column**. It defines both *what columns come back* and *the
  shape of each result*.
- **`Query`** — the conjunctive query, written against the keyed base
  surface (see [Base surface](#base-relation-surface-keyed)).
- **`Bag`** — unified with the list of results, one `Functor(V1, V2, ...)`
  term per returned row, in the argument order of `Template`.

A worked goal:

```prolog
query(
    result(outer_id, name_text, outer_start),
    ( node(id: outer_id, kind: 'function_definition', start_byte: outer_start),
      descendant(outer_id, inner_id),
      node(id: inner_id, kind: 'function_definition'),
      outer_id \= inner_id,
      node(parent_id: outer_id, kind: 'identifier', text: name_text) ),
    Out
)
```

demarcates a **compile-and-ship query**: the conjunction in `Query` is
compiled to one CozoScript script, run against the store's handle, and its
result rows are collected into `Out` as
`[result(Id, Name, Start), ...]`. The `query` wrapper (rather than
bare `?-`-style goals) is what tells the kernel "this is answered by the
backend, not by resolution."

Reduction is **all-at-once, not row-per-branch**. Unlike the earlier
sketch, `query/3` does **not** bind into the resolvent or spawn one
solution branch per row: it behaves like `findall/3`, unifying `Bag` with
the full result list in a single deterministic reduction. Enumerating rows
as branches, occurs-outside projection analysis, and backtracking into the
query are all **removed** by this shape — the interpreter core is untouched
beyond adding the `query/3` clause.

**Precondition.** Every non-projection position in `Query` (every column
constant) must already be **bound to an atom** at reduction time.
Projection is carried entirely by `Template`; the variables in `Template`
are what come back.
## The compiler

**Scope note.** The `query/3` compiler is the unit of work specified here.
The `query/3` `reduce_goal` clause (kernel wiring, `Bag` unification) and
the mnestic adapter callout (schema discovery, `run_script`, row
marshalling) are **separate future issues**; this section is the compiler
contract they build against.

The compiler is split across the seam:

- **Prolog side** parses the keyed `Query`, collects the transitive
  closure of referenced `query_rule/2` derived relations, translates the
  v1 builtins into its own emitted-term functors, and emits **one
  intermediate term** capturing template + derived rules + goals. It does
  **not** emit CozoScript, does **not** *authoritatively* classify
  base-vs-derived (it does a provisional split by `query_rule/2`
  membership — see [Obligations](#the-emitted-term-and-obligations)), and
  does **not** consult the schema.
- **Python side** receives that term, classifies each relation literal as
  base (against the discovered schema) or derived (matches a passed-down
  derived-rule head), transliterates to CozoScript, validates base columns
  and types against the schema, assembles the final script, and runs it.

The reason base-vs-derived classification lives Python-side is that only
Python holds the discovered schema; the Prolog side cannot tell a stored
relation from a *valid* one without it. So Prolog stays schema-free: it
marks as derived only what it can prove derived (a `query_rule/2` head) and
emits every other relation as a base obligation for Python to verify.

### Base-relation surface (keyed)

Base relations are written in a **keyed, dict-ish surface** using the `:`
operator, naming only the columns a goal constrains:

```prolog
node(id: OuterId, kind: 'function_definition', start_byte: OuterStart)
```

This must be **parseable Prolog** but need not be meaningful as ordinary
Prolog — `:` is reused purely as a term constructor (it parses as SWI's
module-qualification operator, `:(id, OuterId)`, which the compiler walks
as a key-value pair). Keying rather than positional arguments is
deliberate: an eleven-column relation is unreadable and brittle
positionally, and the same relation naturally appears with different sets
of keys at different call sites (`node(id: I, kind: K)` vs
`node(parent_id: P, kind: K, text: T)`) without any arity mismatch. The
compiler normalizes each `Key: Value` surface pair to a `Key-Value` pair
in the emitted term.

The **same keyed vocabulary is used everywhere** — in `query/3` `Query`
goals and in the `support`-file `query_rule/2` bodies alike.

### Derived-relation collection

Walking `Query`, any goal whose functor is a `query_rule/2` head is a
**derived relation** (e.g. `descendant`). The Prolog compiler collects the
**transitive closure** of derived relations reachable from the query —
`descendant`'s own body references `descendant`, so recursion must survive
into the emitted term — and emits their clauses as term literals. It does
**not** transliterate them to cozo `:=` rules; Python does that, since
distinguishing a derived-rule body goal from a base match again needs the
schema.

### Builtins and guards (v1 minimal set)

v1 supports exactly:

- `\=/2` — inequality (the demo's `OuterId \= InnerId` guard); the
  surface operator is standard Prolog `\=`, which the compiler translates
  to the internal `'!='` functor (mirroring CozoScript) in the emitted term;
- **column-constant match** — a constant in a keyed base-relation position
  (the demo's `kind: 'function_definition'`).

The Prolog compiler **owns translation of these v1 builtins**: it emits
them with its own functor in the intermediate term (e.g. `'!='` as the
functor of the emitted inequality literal), because Prolog understands its
own terms better than a downstream re-parser would. Any other builtin in a
`Query` is a **hard compile error** Prolog-side. v1 does **not** fall back
to Prolog-side post-filtering. Failing fast keeps the seam honest — an
unsupported construct surfaces immediately rather than silently splitting
evaluation across two engines. The guard set widens deliberately, guard by
guard, as real queries need it.

### Projection

The columns the compiled query returns are exactly the **arguments of
`Template`**, in `Template` argument order. There is no occurs-outside
analysis and no notion of region-local vs. escaping variables: projection
is stated explicitly by the author in `Template`, which is both simpler
and unambiguous. The projection column order is recorded as the **head of
the obligations list** (see [Obligations](#the-emitted-term-and-obligations)).

### The emitted term and obligations

The Prolog compiler emits **one intermediate term**. For the worked
example:

```prolog
compiled_query(
    template(result, [outer_id, name_text, outer_start]),
    derived([
        rule(descendant(anc, desc),
             [ node([id-desc, parent_id-anc]) ]),
        rule(descendant(anc, desc),
             [ descendant(anc, mid), node([id-desc, parent_id-mid]) ])
    ]),
    goals([
        node([id-outer_id, kind-'function_definition', start_byte-outer_start]),
        descendant(outer_id, inner_id),
        node([id-inner_id, kind-'function_definition']),
        '!='(outer_id, inner_id),
        node([id-outer_id, kind-'identifier', text-name_text])
    ])
)
```

Note the surface `Key: Value` pairs have been normalized to `Key-Value`
pairs, and the `!=` guard carries its own functor.

**Transport.** The intermediate term is emitted via `term_to_atom/2` as a
string that Python re-parses; direct Janus hand-off is *not* used, because
Janus marshalling of complex compound terms has proven unreliable. The term
above is the contract; the atom is its serialization.

**Obligations.** The compiler emits an obligations list of the form
`[Projection | Rest]`. The projection column order is the **head**
(`[outer_id, name_text, outer_start]` for the worked example). Each element
of `Rest` is a **base-relation obligation** of the form `Relation(Col1,
Col2, ...)` — `Relation` the relation's functor and `Col*` the columns the
query touched, in no particular order (e.g. `node(id, kind, start_byte,
parent_id, text)`). Prolog emits one such obligation for every relation it
could **not** resolve as a `query_rule/2`-derived head — a *provisional*
base/derived split by `query_rule/2` membership. Python does the
**authoritative** check: it confirms each obligation names a relation that
exists in the discovered schema with those columns; a relation Python
cannot resolve either (neither a schema relation nor a derived rule) is a
hard error. Prolog is thus not fully schema-blind about which literals are
base — it guesses base-by-exclusion and defers verification to Python.

### Prolog-side compiler placement

The Prolog half of the compiler lives as **ordinary Prolog in a sibling
file to `meta.pl`** (the meta-interpreter's own `.pl` source), loaded
alongside it. Concretely it is consulted through the same
`_ensure_*_loaded` pattern `meta.py` already uses to load `meta.pl` and
the foreign-callout module (`importlib.resources` + a process-level
`_consulted` guard). The `query/3` `reduce_goal` clause and the compiler
predicates it calls are thus part of the kernel's loaded Prolog program.
The Python half — schema discovery, base-vs-derived classification,
CozoScript assembly, `run_script`, row marshalling — lives in the mnestic
adapter (below).

## Prolog / Python split

Mirrors the split in [`reduce-goal.md`](reduce-goal.md):

- The **Prolog kernel** owns: the `query/3` `reduce_goal` clause, parsing
  the keyed `Query`, collecting the transitive closure of `query_rule/2`
  derived relations, translating v1 builtins, and emitting the one
  intermediate term + obligations. It does **not** produce CozoScript.
- **Python** owns the **mnestic adapter**: opening the database, schema
  discovery, classifying base-vs-derived relations, assembling the
  CozoScript from the intermediate term, executing it via
  `run_script(script, params, immutable)` against `mnestic.CozoDbPy`, and
  marshalling result rows back into `Bag`.

The kernel reaches the adapter through the existing Janus foreign-callout
path (`foreign(Fn, In, Out)` → `py_call`), the same mechanism the general
store oracle uses. Calling out is **not** a suspension: the backend
answers immediately, so a `query/3` reduces inline (deterministically,
`findall`-style). The callout itself is a **separate future issue**; the
compiler specified above produces the intermediate term it will carry.

### The `run_script` mutability flag

The adapter executes via `run_script(script, params, immutable)`. In v1
every `query/3` is a **read** (`immutable` → read-only), consistent with
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

## The keyed surface is the surface

Earlier drafts proposed a positional `node/11` base predicate with a
separate `node_match([...])` projection *sugar* layered on top. That is
**superseded**: the keyed form (`node(id: X, kind: 'function_definition')`)
is now the one and only base surface, authored directly in both queries and
support rules. There is no positional layer beneath it and no separate
desugaring step. The compiler's only normalization is surface `Key: Value`
→ emitted `Key-Value` pairs, described under
[Base-relation surface](#base-relation-surface-keyed).

## Worked example: nested-function query

The reference query end-to-end, carried over from the standalone
treesitter → mnestic CST pipeline proven in prior work. Schema:

```
*node{id => kind, parent_id?, start_byte, end_byte,
      start_row, start_col, end_row, end_col, is_named, text}
```

Support rules (`support` file): `descendant/2` as the transitive closure
over `parent_id`, in the keyed surface (as shown
[above](#user-support-rules-query_rule2)).

Query:

```prolog
query(
    result(OuterId, NameText, OuterStart),
    ( node(id: OuterId, kind: 'function_definition', start_byte: OuterStart),
      descendant(OuterId, InnerId),
      node(id: InnerId, kind: 'function_definition'),
      OuterId \= InnerId,
      node(parent_id: OuterId, kind: 'identifier', text: NameText) ),
    Out
)
```

Projects `OuterId`, `NameText`, `OuterStart` (named explicitly by
`Template`). `NameText` is the outer function's name, resolved by joining
its direct `identifier` child on `parent_id = OuterId`. Against a file with
a `def outer_function` containing a nested `def inner_function`, `Out`
unifies with a single `result(...)` for `outer_function`. This mirrors the
target CozoScript:

```
descendant[anc, desc] := *node{id: desc, parent_id: anc}
descendant[anc, desc] := descendant[anc, mid], *node{id: desc, parent_id: mid}

?[outer_id, name_text, outer_start] :=
    *node{id: outer_id, kind: 'function_definition', start_byte: outer_start},
    descendant[outer_id, inner_id],
    *node{id: inner_id, kind: 'function_definition'},
    outer_id != inner_id,
    *node{parent_id: outer_id, kind: 'identifier', text: name_text}
```

Note: the correct treesitter node kind is **`function_definition`**
(snake_case CST kind), **not** the stdlib `ast` `FunctionDef`. There is no
`name` column in the schema; a function's name is the text of its direct
`identifier` child, recovered by the join above.

The compiler block's target is exactly this query's intermediate term and
obligations. Running it end-to-end from **inside** `constraint` — the
`query/3` `reduce_goal` clause plus the adapter callout that assembles and
runs the CozoScript above — follows in the subsequent issues, and returns
the same row the standalone pipeline produced.

## Deferred / out of scope for v1

- **Write / load path.** Populating the database from `constraint` is
  entirely out of scope; v1 reads an externally-populated store. When it
  arrives it slots behind the same `run_script(..., immutable)` seam
  (mutating vs read-only), likely as a distinct store-side operation
  rather than a `query/3` query.
- **Neutral query representation.** A backend-independent Prolog term
  language for datalog, with cozo as one compile target behind an
  adapter interface — the real fix for CozoScript lock-in. v1
  deliberately commits to mnestic/CozoScript and builds the concrete
  adapter first; the neutral layer is designed once there are queries
  worth expressing natively.
- **Second backend / the `backend:` key.** Only `rocksdb` mnestic in v1.
  The orthogonal `backend:` encoding is recommended for when a second
  engine appears, not implemented now.
- **Wider builtin / guard set.** Beyond `{\=/2, column-constant
  match}` (e.g. column-column comparison, dropped from v1); aggregation and negation especially are cozo-specific in their
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
