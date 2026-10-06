# adjourn resolutions

adjourn resolves a goal as a coroutine: instead of running to completion in
one shot, resolution advances until it reaches a stopping point, records its
state, and waits to be resumed.

## Sessions

A session is one goal being resolved. Its full state lives on disk, so a
session can be paused at a stopping point and resumed later.

## The lifecycle

A session's status is one of:

- **running**: the session has been created but not yet advanced. This is
  only seen right after the session is initialised. Resolution never pauses
  mid-reduction: the state is written only on creation and when resolution
  stops at one of the states below.
- **suspended**: the program deliberately paused at a `yield` and is waiting.
  The suspension carries a label, an atom the program chose, that says why it
  paused and what it needs.
- **solution**: the goal succeeded with one set of bindings. This is not the
  end: a solution is a resumable checkpoint, and resuming backtracks to look
  for the next solution.
- **done**: all alternatives are exhausted. This is the only terminal state.

## Suspensions

A suspension is the program asking for help. Its label says what it is stuck
on: for example, a missing fact, a choice it cannot make on its own, or an
input it needs. While the session is suspended, the program can be given what
it needs before resolution continues. Resuming without changing anything
continues past the yield.

## Extending the program

Rules are ordinary Prolog clauses. Adding rules registers the new clauses
and points the session at @top, the ruleset containing every registered rule,
so the new rules are in scope when it is next resumed and a goal that was
stuck can now proceed. Adding rules does not itself resume the session.

## The rule language

Rule bodies may use:

- `true`, and conjunction with `,`.
- `\+ Goal`: negation as failure. It succeeds when `Goal` has no solution and
  never binds variables. `Goal` may use any of these constructs except
  `yield`; a `yield` inside a negation is an error.
- `yield(Label)` to suspend, and `checkpoint(Label)` to save the state and
  continue. `Label` must be an atom.
- Calls to predicates defined by rules.
- Host builtins that do not call other goals, such as `=`, `\=`, `==`, `<`,
  `>`, and `is`.

Not supported: disjunction (`;`), if-then-else (`->`), cut (`!`), and
builtins that call goals, such as `findall/3`, `forall/2`, and `call/N`. Write
alternatives as separate clauses instead.
