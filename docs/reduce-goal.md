# Resolution and Clause Dispatch (`reduce_goal`)

> Status: v1 design decisions. Supersedes the SWIPL-modules-vs-namespacing
> handoff question raised in [`rule-scoping.md`](rule-scoping.md).
> Implementation in progress.

## What this doc covers

How the `constraint` meta-interpreter retrieves and dispatches clauses
at resolution time — the mechanism behind `reduce_goal`. The "what must
be supported" lives in [`rule-scoping.md`](rule-scoping.md); this doc
records "how it works."

## Prolog / Python split

`constraint` is not intended to run as a standalone Prolog program.
Python is an integral orchestration layer: I/O, databases, LLM-generated
rules, and the (eventual) clause-selection policy all live there
natively. The architecture reflects this:

- The **Prolog kernel** owns: unification, the resolvent and branch
  machinery, `step`, suspend/resume, branch construction, the
  unifiability filter, and an in-process immutable clause cache.
- **Python** owns the `clauses_for(Hash, PI)` oracle: store dispatch,
  `chain` composition, database / synthesis / LLM-rule backends,
  content-hashing and immutability bookkeeping, the driver loop, and
  the clause-selection policy when it arrives.

The Prolog kernel calls out to Python (via Janus) on cache misses —
inline and automatic. **Calling out is not a suspension**; it is simply
where the backend implementation lives. Suspension is reserved for
genuine external-intervention points: a declared goal whose resolution
requires an external actor (LLM, human) and which *cannot* automatically
proceed. A cache miss can always proceed automatically (Python answers
immediately), so it does not suspend.

## The store interface

The contract every backend implements:

```
clauses_for(+Hash, +PI) -> OrderedClauses    # [Head-Body], in ruleset order
owns(+Hash)                                  # cheap ownership test
```

`PI` is the predicate indicator `Name/Arity`. The interface is
**goal-agnostic**: the oracle returns all clauses defining `PI` in the
scope identified by `Hash`, without seeing the goal's bindings. Goal-
specific unification stays Prolog-side (see [Kernel mechanics](#kernel-mechanics)).
This split is precisely what makes the cache key `(Hash, PI)` — independent
of any particular query — stable and reusable.

A rule set need not be atomic from the dispatcher's view. A backend may
synthesize clauses on the fly (DB query, generator, learned model) as
long as it honors immutability: the same hash must always yield the same
clauses.

## Dispatch

Stores register a priority and implement `owns`. The dispatcher routes a
hash by asking stores in priority order; the first to claim it answers.
Content-addressing makes ownership effectively unique in practice (a
hash identifies specific content); priority only matters for
synthesizing stores whose ownership tests are pattern-based and could
overlap.

A `Hash -> StoreId` registry is a deferred performance optimization for
the concrete-load case. Query-by-`owns` is the v1 mechanism, and it is
acceptable to query every registered store on a miss.

`chain` is **itself a store**. To resolve a `chain` hash, it looks up
its ordered member-hash list, dedups member hashes keep-first, and
resolves each member by **re-dispatching through the top-level
dispatcher**. This is how chains nest and how members can live in
arbitrary backends.

## Composition: `chain`

(Full requirements: [`rule-scoping.md` §R7](rule-scoping.md).)
Operationally:

- The flattened, ordered candidate-clause list of `chain(M1, ..., Mn)`
  for predicate `PI` is the concatenation, in argument order, of each
  `Mi`'s `clauses_for(Mi, PI)`, with repeated member-hashes suppressed
  at the current chain level (best-effort dedup; opaque backends are
  dedup-opaque).
- Associativity holds because keep-first dedup of concatenations is
  associative.
- Composite hash is a Merkle roll-up: `hash(chain, [M1, ..., Mn]_deduped)`.

## Ordering

Block order is **`chain` argument order**, top-down. Intra-block clause
order is **part of the atomic rule set's content** (and its hash) —
explicit data, not a property of any backing store's retrieval order.
Aggregation is plain ordered concatenation; the kernel does not depend
on SWIPL assert order or any other implicit ordering. A backend that
re-imports clauses in a different storage order but preserves the
atomic rule set's declared internal order produces the same hash and
the same resolution behavior.

## Immutability and hashing

Content hashes use canonical-parsed-term form: each clause is
`copy_term`-ed and then `numbervars`-ed so variables are renumbered by
first occurrence. The resulting ground term is serialized and hashed.

- Variant clauses hash equal: `p(X) :- q(X)` and `p(Y) :- q(Y)` are
  the same clause.
- Cosmetic differences (whitespace, variable naming) are invisible.
- Structural differences are preserved: `p(X, X)` and `p(Y, Z)` differ.

An atomic rule set's hash is over the ordered list of canonical
clauses. A composite (`chain`) hash is the Merkle roll-up above.

**Immutability is what makes the kernel's cache trivially correct.** A
given `(Hash, PI)` resolves to a fixed clause list, forever. The cache
is never invalidated; a cold resume in a fresh process simply re-warms
it from the oracle, which is consistent with R4 because the oracle
returns identical immutable content for the same hashes. The cache is
**not** part of serialized session state — only hashes are.

## Kernel mechanics

`reduce_goal` for the general case, in spec form:

```prolog
reduce_goal(G, Gs, Rest, Scope, Event, State1) :-
    functor(G, N, A),
    clauses_for(Scope, N/A, AllClauses),    % cache hit, or transparent Janus call-out + fill
    matching(AllClauses, G, Candidates),
    build_branches(G, Gs, Candidates, Scope, NewBranches),
    append(NewBranches, Rest, NextBranches),
    step(state(NextBranches), Event, State1).

% Filter to clauses whose head unifies with the goal, without binding the goal.
matching([], _G, []).
matching([Head-Body|T], G, [Head-Body|M]) :-
    unifiable(G, Head, _), !,
    matching(T, G, M).
matching([_|T], G, M) :-
    matching(T, G, M).

% Build one branch per surviving candidate, performing the real unification on
% findall-renamed terms (so each branch is independent).
build_branches(G, Gs, Candidates, Scope, NewBranches) :-
    findall(branch(NewGoals, Scope),
            ( member(Head-Body, Candidates),
              G = Head,
              body_to_goals(Body, BodyGoals),
              append(BodyGoals, Gs, NewGoals) ),
            NewBranches).
```

Notes:

- The candidate filter uses **`unifiable/3`**, not `subsumes_term/2`.
  Subsumption is asymmetric: querying `p(X)` against fact `p(a)` is
  unifiable (`X=a`) but `subsumes_term(p(a), p(X))` is false, so a
  subsumption filter would silently drop the fact. The
  resolution-correct relation is unifiability.
- Branches are spliced DFS via `append(NewBranches, Rest, ...)` — the
  first candidate is explored first; the rest remain as resumable
  choice points in the explicit state.
- Branch state is a plain Prolog term (`branch(Goals, Scope)`); the
  whole `state(...)` is fully serializable. The cache is kept in a
  separate dynamic table and is never serialized.
- `clauses_for/3` on the Prolog side is the cache façade: a hit returns
  immediately; a miss transparently invokes the Python oracle via
  Janus, asserts the result, and returns.

## Cut and program purity

v1 assumes pure logic programs — no `!` in rule bodies. Host-level `!`
inside `reduce_goal`'s own implementation is fine and unrelated;
object-level `!` simply has no semantics in v1 rule bodies and would
yield a dead branch if encountered.

The design must not *preclude* introducing object-level cut later. When
it lands, cut is implemented as **branch surgery** on the explicit
state — eliminating designated branches from `state(Branches)` — via
dedicated cut predicates whose state-manipulation semantics are defined
inside `reduce_goal`. The intended scoping is **block-local**: a cut
commits within its originating atomic rule set only, never across
`chain` boundaries. This preserves `chain`'s result-stable character
(cross-block ordering affects enumeration order only, not solution
sets) and avoids reintroducing a need for cross-block priority.

## Deferred / out of scope for v1

- **Provenance / branch tagging.** Branches do not carry origin
  metadata in v1. Cross-version resume of serialized session state is
  **not** guaranteed — the serialized state shape may change between
  early versions, and resuming a state serialized by a previous version
  may require manual manipulation of the state term.
- **Clause-level deduplication** (variant-based; see
  [`rule-scoping.md` §D3](rule-scoping.md)).
- **Object-level cut and proof-of-exhaustion** (see
  [`rule-scoping.md` §D4](rule-scoping.md)).
- **Clause-selection policy.** A learned or otherwise programmable
  ordering / selection over the candidate list slots in **inside the
  oracle**, between dispatch and return. v1 returns candidates in
  `chain` order with no further selection.
- **Registry-based dispatch** as a performance layer over the current
  query-by-`owns` mechanism.
