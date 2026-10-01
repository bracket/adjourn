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
  The suspension carries a label, an arbitrary term the program chose, that
  says why it paused and what it needs.
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

Rules are ordinary Prolog clauses. Adding rules makes the new clauses
available and sets the session to restart the current goal from the top when
it is next resumed, so a goal that was stuck can now proceed. Adding rules
does not itself resume the session.
