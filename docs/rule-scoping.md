# Rule Scoping in `constraint`

> Status: requirements settled (this document). Mechanism — SWIPL modules
> vs. own assert/retract namespacing vs. hybrid — to be decided in a
> following design block.

## Framing

A **scope** is the set of rules `reduce_goal` may match against when
resolving a goal at a given point in a resolution. These requirements
constrain *resolution-time rule lookup*, independent of where rules
physically live (RocksDB, files, Python-side extractors, LLM-generated
mid-resolution). The intent of running the Prolog interpreter inside
Python is precisely to keep rule storage and origin flexible; the scoping
model must therefore sit *above* any storage or module mechanism.

## Core requirements

### R1 — Named rule sets
A **rule set** is a name bound to a set of clauses (rules defining terms).
Naming is a first-class `constraint` concept, conceptually transparent as
`name = { set of rules }`. It is explicitly DISTINCT from SWIPL/Janus
modules; those modules may be used to *implement* rule sets but are not
the user-facing model.

### R2 — Versioning of rule sets
A rule-set name resolves to a **version**, where a version is a content
hash of the rule set (git-like). A `(name, hash)` pair is immutable. The
"live" binding of a name may advance to new versions as content changes.
Versioning is required, not optional: it is the indirection that makes
snapshot semantics (R4) possible without serializing the rule set itself.
"New name per version" is insufficient — the *same name* a resolution was
bound to must remain resolvable to its historical content.

Content hashing gives a free property: identical rule content yields an
identical version id, so "did the rules change" is a cheap hash compare.
This hash MUST be the same hash the runtime layer records as "rule hash at
suspension" — the two mechanisms are one, and the doc should not let them
drift apart.

### R3 — Per-branch scope binding
The active scope is a property of an individual resolution **branch**, not
of the resolution as a whole. Each branch carries a binding map from
rule-set names to pinned versions. This is required, not merely chosen: it
is the same mechanism that enables R4 and the intentional-redirect use
case (R5). Consequence: the meta-interpreter branch state gains a scope
component (today `branch(Goals)` → roughly `branch(Goals, ScopeBinding)`),
and `reduce_goal` consults the branch's binding rather than a hardcoded
module.

### R4 — Snapshot semantics on resume
On resume, a resolution sees rule sets **as they were at suspension
time**. Serialized session state pins immutable `(name, hash)` references,
not bare names. Rule of thumb: *a resolution continues as if it had never
been suspended, no matter how far apart in time* — unless the user has
intentionally redirected it (R5). This refines the runtime layer's
"unexpanded goals see current rules" position: unexpanded goals see the
current rules *of their pinned version*, fixed once bound.

### R5 — Intentional redirection
The user may deliberately change the rules in effect and re-run a
resolution (or part of it): rebind a branch to a different rule-set
version (or to a live name), then re-run from a chosen point. This must be
an *explicit, intentional* act — it is the only way the snapshot guarantee
of R4 is broken.

### R6 — Scope in serialized session state
The per-branch scope binding (R3) is part of the serialized session state,
alongside the existing goal + rule hash + committed trace. Resume is
otherwise ambiguous.

### R7 — Rule-set composition (union, explicit)
Rule sets compose. The single composition operator is **union**:
`union(A, B, …)` is a rule set whose clauses are the set-union of its
members' clauses. Intersection and complement are deliberately excluded —
union-only keeps "what rules are in effect" monotonic and inspectable
(every member contributes; nothing is shadowed or subtracted), which is
essential for reasoning about per-branch scope (R3) and resume (R4).

Composition is **always explicit**. Dotted naming (`name.subname`) is a
pure namespace-organization convention and does NOT imply auto-union:
`name.sub1` and `name.sub2` are distinct entities, and nothing is unioned
until an explicit declaration pulls them in — analogous to C++ namespaces,
where `using namespace name;` is the explicit act, not the mere existence
of `name::`. The disanalogy to record: a C++ `using` is lexical and
static, whereas a `constraint` scope binding is dynamic and per-branch —
it may differ down two branches of one resolution and is part of
serialized state. The mental model is "the active set of `using`
declarations, attached to a branch rather than a translation unit."

A composite's version is the hash of its members' hashes (Merkle-style
roll-up): `global = union(conventions, observed, spec_pack_python, …)` is
pinned once each member's `(name, hash)` is pinned. A branch binding (R3)
therefore pins a composite transitively to the set of member `(name,
hash)` pairs; no new machinery is needed. `reduce_goal` matches a goal
against the union of all clause sets the branch's resolved scope expands
to — order-independent, since union is commutative.

The common case is a top-level rule set defined as an explicit union of
many named sets.

## Deferred

### D1 — Observed KB vs Expected KB distinction
Not a scoping primitive. Expressible as a convention over named rule sets
(R1) and union (R7). Treating it as primitive would bake the original
repo-validation framing into the core; `constraint` is intended to
generalize beyond that.

### D2 — Rule provenance / origin tracking
Useful for debugging, auditing LLM-generated rules, and later
imitation-learning traces, but it is metadata *on* rules and does not
change what `reduce_goal` sees. Easy to add later as a tag; no mechanism
needs reserving now.

## Handoff to the mechanism block

The central mechanism task: design the per-branch `name → (version) hash`
binding map — its representation, how versioned rule sets are stored and
content-addressed, how `reduce_goal` queries the union expansion, and
which of SWIPL modules / own assert-retract namespacing / hybrid
implements it. R2+R3+R4+R7 all reduce to this one binding-map design.
