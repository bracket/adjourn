# Rule Scoping in `constraint`

> Status: requirements settled. R7's original "union, commutative" framing
> is superseded by `chain` (ordered, non-commutative); R1 and R2 tightened
> with internal-order and canonical-hashing requirements respectively.
> Mechanism design for clause dispatch and `reduce_goal` lives in
> [`reduce-goal.md`](reduce-goal.md).

## Framing

A **scope** is the set of rules `reduce_goal` may match against when
resolving a goal at a given point in a resolution. These requirements
constrain *resolution-time rule lookup*, independent of where rules
physically live (RocksDB, files, Python-side extractors, LLM-generated
mid-resolution). The intent of running the Prolog interpreter inside
Python is precisely to keep rule storage and origin flexible; the scoping
model must therefore sit *above* any storage or module mechanism.

**Out of scope for v1: namespace-level scoping.** Atomic rule sets are
the unit of authorship; a user who wants namespace separation handles
name mangling themselves. This may be revisited if a clear need emerges
— nothing in the mechanism precludes it — but the v1 mechanism deals
only with versioned content-addressed scoping.

## Core requirements

### R1 — Named rule sets
A **rule set** is a name bound to a set of clauses (rules defining terms).
Naming is a first-class `constraint` concept, conceptually transparent as
`name = { ordered sequence of rules }`. It is explicitly DISTINCT from
SWIPL/Janus modules; those modules may be used to *implement* rule sets
but are not the user-facing model.

Atomic rule sets are **internally ordered**: the clause sequence is part
of the rule set's content (and therefore part of its hash, R2). Order is
explicit data, not a property of any backing store's retrieval behavior.
A backend that loses or reorders clauses fails the contract.

### R2 — Versioning of rule sets
A rule-set name resolves to a **version**, where a version is a content
hash of the rule set (git-like). A `(name, hash)` pair is immutable. The
"live" binding of a name may advance to new versions as content changes.
Versioning is required, not optional: it is the indirection that makes
snapshot semantics (R4) possible without serializing the rule set itself.
"New name per version" is insufficient — the *same name* a resolution was
bound to must remain resolvable to its historical content.

The content hash of an atomic rule set is computed over its clauses in
authored order, after each clause has been **canonicalized**: variables
renumbered by first occurrence (e.g. via `copy_term` + `numbervars`),
then the resulting ground term serialized and hashed. Consequences:

- *Formatting-independent* — whitespace and presentation do not affect identity.
- *Variable-rename stable* — `p(X) :- q(X)` and `p(Y) :- q(Y)` hash equal.
- *Structurally discriminating* — `p(X,X)` and `p(Y,Z)` hash differently.

Content hashing gives a free property: identical canonical content yields
an identical version id, so "did the rules change" is a cheap hash compare.
This hash MUST be the same hash the runtime layer records as "rule hash at
suspension"; the two mechanisms are one. Note that, given per-branch
scoping (R3), the runtime's *singular* hash field generalizes to a per-
branch resolved-scope hash — the unification still holds, just at branch
granularity.

### R3 — Per-branch scope binding
The active scope is a property of an individual resolution **branch**, not
of the resolution as a whole. Each branch carries a binding map from
rule-set names to pinned versions. This is required, not merely chosen: it
is the same mechanism that enables R4 and the intentional-redirect use
case (R5). Consequence: the meta-interpreter branch state gains a scope
component (today `branch(Goals)` → `branch(Goals, ScopeBinding)`), and
`reduce_goal` consults the branch's binding rather than a hardcoded
module.

### R4 — Snapshot semantics on resume
On resume, a resolution sees rule sets **as they were at suspension
time**. Serialized session state pins immutable `(name, hash)` references,
not bare names. Rule of thumb: *a resolution continues as if it had never
been suspended, no matter how far apart in time* — unless the user has
intentionally redirected it (R5).

In the mechanism, this falls out automatically from immutability: a
pinned hash always resolves to identical clause content. See
[`reduce-goal.md`](reduce-goal.md) for how the immutable `clauses_for`
oracle realizes this without serializing the clauses themselves.

### R5 — Intentional redirection
The user may deliberately change the rules in effect and re-run a
resolution (or part of it): rebind a branch to a different rule-set
version (or to a live name), then re-run from a chosen point. This must
be an *explicit, intentional* act — it is the only way the snapshot
guarantee of R4 is broken.

### R6 — Scope in serialized session state
The per-branch scope binding (R3) is part of the serialized session
state, alongside the existing goal + rule hash + committed trace. Resume
is otherwise ambiguous.

### R7 — Rule-set composition (`chain`, ordered)
The composition operator is **`chain`** — ordered, associative
concatenation of rule sets with first-occurrence ruleset-level dedup.
The original "union, commutative" framing is superseded.

- **Ordered.** The argument order of `chain(A, B, C, ...)` is the block
  order in which clauses are presented to resolution. This is
  intentional: fine-grained author control over enumeration order is
  desirable and is not something the user should have to recover by
  authoring an external priority structure.
- **Associative.** `chain(chain(A,B), C) = chain(A, chain(B,C)) =
  chain(A, B, C)`. Keep-first ruleset-hash dedup preserves associativity
  (pre-deduping either operand of a concatenation cannot change the
  final keep-first result).
- **Identity** = the empty rule set ∅. So `(chain, ∅)` is a monoid.
- **Not commutative.** `chain(A, B)` and `chain(B, A)` are distinct
  compositions with distinct hashes. This is the cost of (and the lever
  for) giving the author control over block order.
- **Unique.** Dedup is at the rule-set hash level (keep first
  occurrence): if the same atomic rule set appears via two paths, the
  second occurrence's clauses are suppressed. Dedup is best-effort at
  the structure the dispatcher can see — opaque/synthesizing backends
  are dedup-opaque — which is acceptable under v1's pure-logic-program
  assumption (see D4). Clause-level dedup (across distinct rule sets)
  is deferred and is **decoupled from identity** (see D3): adding it
  later does not change any hashes.
- **Hash.** A composite's hash is a Merkle roll-up over (operator tag,
  ordered member hashes after ruleset-hash dedup keep-first).

Within an atomic rule set, the internal clause order (R1) is preserved
through composition: `chain` concatenates each member's ordered clauses
in turn. The flattened, ordered clause sequence of a composite is the
in-order traversal of its members (member-hashes deduped keep-first),
each visited rule set contributing its clauses in internal order.

Intersection and complement remain deliberately excluded: keeping
composition monotonic (every visible member contributes; nothing is
shadowed or subtracted) is essential for clear reasoning about
per-branch scope (R3) and resume (R4).

## Deferred

### D1 — Observed KB vs Expected KB distinction
Not a scoping primitive. Expressible as a convention over named rule
sets (R1) and `chain` (R7). Treating it as primitive would bake the
original repo-validation framing into the core; `constraint` is
intended to generalize beyond that.

### D2 — Rule provenance / origin tracking
Useful for debugging, auditing LLM-generated rules, and later
imitation-learning traces, but it is metadata *on* rules and does not
change what `reduce_goal` sees. Easy to add later as a tag; no mechanism
needs reserving now.

### D3 — Clause-level deduplication
A composition that produces the same clause from two distinct rule sets
currently yields a redundant (but correct) duplicate branch. Tightening
to clause-level uniqueness is deferred; when added, identity is
**variant-based** (`p(X) ≡ p(Y)` up to consistent renaming), and the
change is hash-neutral — composite identity depends only on the
composition tree and member hashes (R7), not on whether resolution
dedups across distinct members. Some backends may enforce clause
uniqueness internally (e.g. a database with a unique index on canonical
form), independently of this default.

### D4 — Object-level cut and proof-of-exhaustion
v1 assumes pure logic programs without cut. The mechanism is designed
not to *preclude* introducing object-level cut later, implemented as
block-local "branch surgery" on the explicit search state (see
[`reduce-goal.md`](reduce-goal.md) §"Cut and program purity"). A
proof-of-exhaustion / negation-as-failure operator is anticipated as a
related future need.

## Handoff

The mechanism design — clause dispatch, the Prolog/Python split,
`reduce_goal` flow, the `clauses_for` oracle, canonical hashing, the
immutability-backed cache — is documented in
[`reduce-goal.md`](reduce-goal.md), which supersedes the original
handoff question (SWIPL modules vs own assert-retract namespacing vs
hybrid). The user-facing model is the `clauses_for(Hash, PI)` store
contract; SWIPL's term database is one possible backend among several,
not the architectural commitment.
