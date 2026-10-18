# Cut (`!`) in the adjourn metalanguage

## Goal

Give `!` real meaning in L3 rule bodies. Today `!` reaches `reduce_goal/6`
in `src/adjourn/meta.pl`, falls through `goal_kind/2` as a visible
builtin, and is silently a no-op.

Scope is strictly `!`. `->`, `;`, `once/1` and other cut-derived
constructs are out of scope.

## Backtracking model (unchanged)

The branch list in `state(Branches)` is already the choice-point stack.
`rule_branches/4` materializes every matching clause as its own
`branch(OrigGoal, Goals)` eagerly, and `reduce_user_goal(rules, ...)`
prepends them to `Rest` in DFS order. A failed goal drops its branch, and
the next branch takes over. Bindings never need undoing because each
branch holds its own copies. No new backtracking machinery is added.
Cut is implemented purely as pruning of this list.

## Representation: positional barrier levels

The branch list holds two kinds of entries:

- `branch(OrigGoal, Goals)`
- the bare atom `barrier`

A barrier carries no payload. Its identity is its **level**: the number
of barriers behind it in the list.

### Invariant

A barrier's level never changes while it exists. Entries leave the list
only from the front (exhaustion or failure), or as a prefix removed by a
cut. Neither operation can touch anything behind a barrier until that
barrier itself has been removed. The list structure therefore serves as
the counter, so no barrier ids and no id counter exist in the state.

### Call time (`reduce_user_goal(rules, ...)`)

1. Let K be the number of barriers in `Rest`.
2. Build the alternatives as today. While converting each clause body
   (`body_to_goals/2`, with K threaded in), rewrite `!` to `'$cut'(K)`.
3. If any alternative contains `'$cut'(K)`, the next list is
   `NewBranches ++ [barrier | Rest]`. Otherwise it is
   `NewBranches ++ Rest`, unchanged from current behavior. Barriers are
   inserted only at choice points that need one.

`'$cut'(K)` is ground. It therefore survives the findall copy in
`rule_branches/4` and the pack round-trip. A fresh-variable barrier id
would not survive: findall severs variable identity, which is the same
pitfall as the old per-branch bindings bug.

### Reducing `'$cut'(K)`

1. Let N be the number of barriers in `Rest`.
2. Drop entries from the front of `Rest` until N − K barriers have been
   dropped, stopping immediately after the last one dropped.
3. Continue the current branch with its remaining goals.

This removes the sibling alternatives of the call and every branch pushed
by subgoals before the cut. It also removes inner barriers (levels > K)
and the call's own barrier (level K).

The call's barrier is guaranteed to exist when its cut runs, because the
cutting branch descends from the call. A call's barrier sits behind all
of the call's descendants, so it cannot reach the front while any
descendant is alive. N ≥ K + 1 always holds. A violation is an internal
error.

### Barrier at the front

A barrier at the front means every alternative of that call is
exhausted. Skip it:

    step(state([barrier|Rest]), E, S) :- step(state(Rest), E, S).

### Worked example

Rules: `p :- q, !, r.` and `p :- s.`, where `q` has two clauses and
neither clause contains a cut. `p` is called with K barriers already in
`Rest`.

    [b(q, '$cut'(K), r), b(s), barrier, ...Rest]                    % p pushes barrier at level K
    [b(q1.., '$cut'(K), r), b(q2.., '$cut'(K), r), b(s), barrier, ...Rest]  % q: no cut, no barrier
    '$cut'(K) on the q1 branch: N = K+1, drop through 1 barrier
    [b(r), ...Rest]

Both `q2` and `p :- s` are pruned.

## Scoping

- `!` is permitted only in rule bodies.
- **Top-level goal:** `init/2` is unchanged, so a raw `!` in the
  top-level goal reaches `reduce_goal/6` unrewritten. A new clause there
  throws `error(cut_outside_rule_body, context(reduce_goal/6, _))`. This
  also replaces today's silent no-op for any unrewritten `!`.
- **`\+ G`:** the cut is local to the negation, as in standard Prolog.
  `provable/1` (for `\+`) treats `G` as a body at barrier level 0. `G`
  goes through `body_to_goals/2` with K = 0. If the result contains
  `'$cut'(0)`, the nested state is `state([branch(G, Goals), barrier])`.
  Levels inside the nested proof are relative to its own fresh state, so
  no other special handling is needed.

## Reserved names (load-time, L1)

Rejection happens at L1, in Python, when clauses are parsed or registered
into the store. It does not happen at L2 consult time. Rejected:

- any clause defining `'$cut'/1`
- any clause whose head is `!`

Error: `reserved_predicate('$cut'/1)`, or the analogous form for `!`.

## Errors

Exactly two new errors exist, per anti-gold-plating:

- `error(cut_outside_rule_body, context(reduce_goal/6, _))`
- the load-time `reserved_predicate(...)` rejection

No further error taxonomy is introduced.

## Serialization and state schema

- The state schema bumps from v0 (current: `init_state` in
  `src/adjourn/state.py` returns `"version": 0`) to v1.
- In the JSON state, a barrier appears in `branches[]` as the bare string
  `"barrier"`, interleaved with the existing
  `{"orig_goal": ..., "goals": [...]}` dicts.
- Affected code paths:
  - `parse_packed_branches/2` and `flatten_with_markers/2` in `meta.pl`
    gain a barrier marker.
  - `_unflatten_branches` and `_build_packed_atom` in `meta.py` handle the
    `"barrier"` entry in both directions.
  - `init_state` emits version 1.
- v0 state files are rejected outright under v1 code. They are not
  accepted as-is, and they are not upgraded.

## Effects and backtracking (decided stance, not implemented here)

Effects outside the branch term, such as yield responses, foreign calls,
and plugin-provided context operations like `context_push`/`context_pop`,
are not undone when a branch dies. The stance is committed semantics plus
user-enforced idempotency: handlers should be safe to re-run on a sibling
branch. Effect state is deliberately **not** made branch-local in the
branch term. Cut reduces the practical exposure here: `yield(L), !` is
the idiom for committing to an answer and discarding the alternatives.

## Open questions

- Context operations (`context_push`/`context_pop`, plugin-side) need
  their own design pass for their interaction with branches and cut.
