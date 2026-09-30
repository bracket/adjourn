# Driving an adjourn resolution

adjourn resolves a goal as a *coroutine*: instead of running to completion in
one shot, it advances a step at a time and hands control back to you at
decision points. You drive it forward until it reaches an answer or runs out
of ways to proceed.

## Sessions

A *session* is one goal being resolved. Its full state lives on disk, so a
session can be advanced, paused, and picked up again later. Each action you
take reads the current state, advances it, and writes the new state back.

## The lifecycle

Every action returns the session's status, which is one of:

- **running** — the session has been created but not yet advanced. You only
  see this right after the session is initialised. Resolution never pauses
  mid-reduction for you to inspect: the state is written only on creation and
  when resolution stops at one of the states below.
- **suspended** — the program deliberately paused at a `yield` and is waiting
  on you. The suspension carries a *label*, an arbitrary term the program
  chose, that tells you why it paused and what it needs.
- **solution** — the goal succeeded with one set of bindings. This is *not*
  the end: a solution is a resumable checkpoint. Advancing again backtracks to
  look for the next solution.
- **done** — all alternatives are exhausted. This is the only terminal state.

## Suspensions

When a session suspends, read the label. It is the program telling you what it
is stuck on — for example, a missing fact, a choice it cannot make on its own,
or an input it needs. Your job is to give it what it needs and then let it
continue.

## Extending the program

If the program suspended because no rule covers a goal, you can add rules to
the program. Adding rules makes the new clauses available and then continues
resolution from the top of the current goal, so the goal that was stuck can
now proceed. Rules are ordinary Prolog clauses.

## The loop

You are in a loop:

1. Look at the current status and, when suspended, its label.
2. Decide what the program needs: more rules, a resolution of the suspension,
   or simply to be advanced.
3. Act, then read the new status.
4. Repeat until the goal reaches a solution you accept, or until it is done.
