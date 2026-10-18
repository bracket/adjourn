% meta.pl
%
% Continuation-style meta-interpreter with explicit suspension/resumption.
% The interpreted program is given by rule/2 facts loaded separately.
%
% This module is the canonical meta-interpreter for the adjourn package.
% It is located inside the Python package source tree so it is accessible
% via importlib.resources.

:- module(adjourn_meta, [
    init/2,
    step/3,
    step_packed/4,
    parse_packed_branches/2
]).

:- use_module(library(janus)).

% rule/2 is multifile in the user module so that any consulted ruleset can
% add rule/2 facts without module qualification.
:- multifile user:rule/2.

% --- State representation ---
% state(Branches)
% Branches contains branch(OrigGoal, Goals) entries and positional barrier
% atoms.  Goals is the resolvent (the remaining goals to prove) for this
% branch.  OrigGoal is this branch's OWN copy of the original goal term; its
% variables are shared with the goals in this branch's resolvent, so bindings
% established while reducing the resolvent are reflected in OrigGoal.  A
% barrier marks a cut scope; its level is the number of barriers behind it.

% init(+Goal, -State)
% Construct the initial interpreter state for a single goal.  The sole branch
% shares its OrigGoal with its resolvent (both are Goal, the same term).
init(Goal, state([branch(Goal, [Goal])])).

% step(+State0, -Event, -State1)
% Reduce goals until something reportable happens.  Possible events:
%   done            - all branches exhausted
%   solution(Goal)  - the first branch has an empty resolvent
%   suspended(L)    - the first goal was yield(L)
%   checkpoint(L)   - the first goal was checkpoint(L)

step(state([]), done, state([])) :- !.

% First branch has no remaining goals: emit a solution.  The branch's OrigGoal
% is now fully bound and is dropped along with the (empty) resolvent.
step(state([branch(SolvedOrigGoal, [])|Rest]), solution(SolvedOrigGoal), state(Rest)) :- !.

% A barrier at the front means its call alternatives have been exhausted.
step(state([barrier|Rest]), Event, State1) :- !,
    step(state(Rest), Event, State1).

% Otherwise, reduce one goal from the head of the current resolvent, carrying
% this branch's OrigGoal so newly-created branches keep sharing its variables.
% The goal is checked before dispatch: an unbound goal would otherwise unify
% with the head of the first reduce_goal/6 clause.
step(state([branch(OrigGoal, [G|Gs])|RestBranches]), Event, State1) :-
    ensure_plain_goal(G),
    reduce_goal(OrigGoal, G, Gs, RestBranches, Event, State1).

% ensure_plain_goal(+G)
% Reject goals the interpreter cannot reduce: an unbound goal, or a
% module-qualified goal (modules are not part of the interpreted language).
ensure_plain_goal(G) :- var(G), !,
    throw(error(instantiation_error, context(reduce_goal/6, _))).
ensure_plain_goal(M:G) :- !,
    throw(error(module_qualified_goal(M:G), context(reduce_goal/6, _))).
ensure_plain_goal(_).

% --- Goal reduction rules (continuation style) ---
%
% reduce_goal(+OrigGoal, +G, +Gs, +Rest, -Event, -State1)
% Each goal form is handled by exactly one clause (hence the cuts).  A goal
% that fails does not make reduce_goal/6 fail: the branch dies explicitly
% (see branch_survives/4) and resolution continues with the remaining
% branches.

% true: trivially succeeds; drop it and continue.
reduce_goal(OrigGoal, true, Gs, Rest, Event, State1) :- !,
    step(state([branch(OrigGoal, Gs)|Rest]), Event, State1).

% A rewritten cut drops alternatives through the barrier for its call.
reduce_goal(OrigGoal, '$cut'(K), Gs, Rest, Event, State1) :- !,
    barrier_count(Rest, BarrierCount),
    BarriersToDrop is BarrierCount - K,
    drop_through_barriers(Rest, BarriersToDrop, PrunedRest),
    step(state([branch(OrigGoal, Gs)|PrunedRest]), Event, State1).

% A raw cut is only valid after it has been rewritten in a rule body.
reduce_goal(_, !, _, _, _, _) :- !,
    throw(error(cut_outside_rule_body, context(reduce_goal/6, _))).

% conjunction: flatten (A,B) into [A, B | Gs].
reduce_goal(OrigGoal, (A,B), Gs, Rest, Event, State1) :- !,
    step(state([branch(OrigGoal, [A,B|Gs])|Rest]), Event, State1).

% \+ G: negation as failure.  G is proved by the interpreter itself (so it
% can use rule/2 predicates) in a nested resolution; the branch survives only
% if that proof finds no solution.  No bindings from the proof leak out.
reduce_goal(OrigGoal, \+ G, Gs, Rest, Event, State1) :- !,
    branch_survives(\+ provable(G), branch(OrigGoal, Gs), Rest, Next),
    step(state(Next), Event, State1).

% yield(Label): cooperative suspension point.  The yield/1 goal is removed
% from the resolvent, so resuming from this state continues after it.
reduce_goal(OrigGoal, yield(Label), Gs, Rest, suspended(Label), state([branch(OrigGoal, Gs)|Rest])) :- !.

% checkpoint(Label): persist the continuation, then continue.  The
% checkpoint/1 goal is removed from the resolvent, so resuming continues
% past it.
reduce_goal(OrigGoal, checkpoint(Label), Gs, Rest, checkpoint(Label), state([branch(OrigGoal, Gs)|Rest])) :- !.

% foreign(Fn, In, Out): invoke a registered Python function synchronously via
% py_call/2 (library(janus)).  Errors raised by the call propagate.  If the
% result does not unify with Out, the branch dies like any failed unification.
reduce_goal(OrigGoal, foreign(Fn, In, Out), Gs, Rest, Event, State1) :- !,
    py_call(adjourn_foreign:dispatch(Fn, In), Result),
    branch_survives(Out = Result, branch(OrigGoal, Gs), Rest, Next),
    step(state(Next), Event, State1).

% query(Store:Template, Query, Bag): compile the query, then reduce it as a
% foreign(mnestic_query, ...) callout followed by building the result terms.
reduce_goal(OrigGoal, query(Store:Template, Query, Bag), Gs, Rest, Event, State1) :- !,
    compile_query(query(Store:Template, Query, Bag), CompiledAtom, Obligations),
    term_to_atom(Obligations, ObligationsAtom),
    Template =.. [F|_],
    step(state([branch(OrigGoal, [
        foreign(mnestic_query, [CompiledAtom, ObligationsAtom], Rows),
        build_query_results(F, Rows, Bag)
      | Gs]) | Rest]), Event, State1).

% General case: a user goal, resolved against user:rule/2 or the host.
reduce_goal(OrigGoal, G, Gs, Rest, Event, State1) :-
    goal_kind(G, Kind),
    reduce_user_goal(Kind, G, OrigGoal, Gs, Rest, Next),
    step(state(Next), Event, State1).

% goal_kind(+Goal, -Kind)
% rules   - user:rule/2 defines Goal's functor/arity
% builtin - Goal is a predicate visible in the host's user module
% unknown - neither
goal_kind(Goal, rules)   :- has_rules(Goal), !.
goal_kind(Goal, builtin) :- predicate_property(user:Goal, visible), !.
goal_kind(_,    unknown).

% reduce_user_goal(+Kind, +Goal, +OrigGoal, +Gs, +Rest, -Next)
% Compute the next branch list for a user goal of the given kind.
reduce_user_goal(rules, Goal, OrigGoal, Gs, Rest, Next) :-
    barrier_count(Rest, K),
    rule_branches(Goal, OrigGoal, Gs, K, NewBranches, HasCut),
    add_call_barrier(HasCut, NewBranches, Rest, Next).
reduce_user_goal(builtin, Goal, OrigGoal, Gs, Rest, Next) :-
    branch_survives(user:Goal, branch(OrigGoal, Gs), Rest, Next).
reduce_user_goal(unknown, Goal, _, _, _, _) :-
    throw(error(unknown_goal(Goal), context(reduce_goal/6, Goal))).

% has_rules(+Goal)
% True if user:rule/2 has any rule for Goal's functor/arity.  Tested on a
% fresh skeleton, NOT the goal instance itself.  This distinguishes "defined
% predicate, but no clause matches this instance" (an ordinary failure: the
% branch dies) from "no such predicate at all" (an error).  It also must not
% bind any variables of the goal, since they are shared with OrigGoal and the
% continuation.
has_rules(Goal) :-
    functor(Goal, Functor, Arity),
    functor(Skeleton, Functor, Arity),
    \+ \+ user:rule(Skeleton, _).

% rule_branches(+Goal, +OrigGoal, +Gs, +K, -Branches, -HasCut)
% One branch per rule whose head matches Goal.  When none match, Branches is
% [] and the current branch simply drops out of the state.  findall/3 copies
% each template, which is exactly what we want: distinct alternatives must be
% able to bind the goal's variables to distinct values.  OrigGoal (and Goal)
% are copied INSIDE the template as OGCopy/GoalCopy, so each branch gets its
% own OrigGoal copy whose variables are shared, through the head unification,
% with that branch's resolvent.  This is what lets a solution recover the
% goal's bindings for that branch.
rule_branches(Goal, OrigGoal, Gs, K, Branches, HasCut) :-
    findall(branch(OGCopy, NewGoals, BodyHasCut),
            ( copy_term(OrigGoal-Goal-Gs, OGCopy-GoalCopy-GsCopy),
              user:rule(GoalCopy, Body),
              body_to_goals(Body, K, BodyGoals),
              body_has_cut(BodyGoals, K, BodyHasCut),
              append(BodyGoals, GsCopy, NewGoals)
            ),
            RawBranches),
    split_rule_branches(RawBranches, Branches, HasCut).

% provable(+G)
% True if the interpreter finds at least one solution for G.  The proof runs
% to its first event: a solution proves G, exhaustion (done) fails, and a
% checkpoint is stepped past (there is nothing to persist from inside a nested
% proof).  A yield cannot suspend a nested proof, so it is an error.
provable(G) :-
    body_to_goals(G, 0, Goals),
    negation_state(G, Goals, State),
    prove(State).

% negation_state(+G, +Goals, -State)
% Cuts in a negated body have a local barrier at level zero.
negation_state(G, Goals, state([branch(G, Goals), barrier])) :-
    body_has_cut(Goals, 0, yes), !.
negation_state(G, Goals, state([branch(G, Goals)])).

prove(State) :-
    step(State, Event, State1),
    proof_event(Event, State1).

proof_event(solution(_),   _).
proof_event(checkpoint(_), State1) :- prove(State1).
proof_event(suspended(L),  _) :-
    throw(error(yield_in_negation(L), context(reduce_goal/6, _))).

% branch_survives(+Test, +Branch, +Rest, -Next)
% If Test succeeds (first solution only), Branch stays at the front;
% otherwise the branch dies and resolution continues with Rest.
branch_survives(Test, Branch, Rest, [Branch|Rest]) :- call(Test), !.
branch_survives(_,    _,      Rest, Rest).

% body_to_goals(+Body, +K, -Goals)
% Convert a rule body into a flat goal list (resolvent segment).  An unbound
% body is kept as a single goal (so reducing it raises an instantiation
% error) rather than unifying with the true/0 or (,)/2 clause heads.  Cuts in
% the body are rewritten to carry the positional barrier level at call time.
body_to_goals(Body, _, [Body]) :- var(Body), !.
body_to_goals(true, _, []) :- !.
body_to_goals((A,B), K, Goals) :- !,
    body_to_goals(A, K, GA),
    body_to_goals(B, K, GB),
    append(GA, GB, Goals).
body_to_goals(!, K, ['$cut'(K)]) :- !.
body_to_goals(A, _, [A]).

% barrier_count(+Branches, -Count)
% Count the positional cut barriers in the choice-point list.
barrier_count([], 0).
barrier_count([barrier|Rest], Count) :- !,
    barrier_count(Rest, RestCount),
    Count is RestCount + 1.
barrier_count([_|Rest], Count) :-
    barrier_count(Rest, Count).

% drop_through_barriers(+Branches, +Count, -Remaining)
% Discard the prefix through Count barriers, including the barriers.
drop_through_barriers(Rest, 0, Rest) :- !.
drop_through_barriers([barrier|Rest], Count, Remaining) :- !,
    NextCount is Count - 1,
    drop_through_barriers(Rest, NextCount, Remaining).
drop_through_barriers([_|Rest], Count, Remaining) :-
    drop_through_barriers(Rest, Count, Remaining).

% body_has_cut(+Goals, +K, -HasCut)
% Inspect without unifying a variable body goal with the cut marker.
body_has_cut([Goal|_], K, yes) :-
    nonvar(Goal),
    Goal = '$cut'(K), !.
body_has_cut([_|Goals], K, HasCut) :-
    body_has_cut(Goals, K, HasCut).
body_has_cut([], _, no).

% split_rule_branches(+RawBranches, -Branches, -HasCut)
% Remove temporary body cut flags while retaining whether this call needs a
% barrier.  Only body flags count; continuation goals may carry an outer cut.
split_rule_branches([], [], no).
split_rule_branches(
    [branch(OrigGoal, Goals, BodyHasCut)|Rest],
    [branch(OrigGoal, Goals)|Branches],
    HasCut
) :-
    split_rule_branches(Rest, Branches, RestHasCut),
    combine_cut_flags(BodyHasCut, RestHasCut, HasCut).

combine_cut_flags(yes, _, yes) :- !.
combine_cut_flags(no, RestHasCut, RestHasCut).

% add_call_barrier(+HasCut, +NewBranches, +Rest, -Next)
% Insert a call's barrier after its alternatives only when its own body cuts.
add_call_barrier(yes, NewBranches, Rest, Next) :-
    append(NewBranches, [barrier|Rest], Next).
add_call_barrier(no, NewBranches, Rest, Next) :-
    append(NewBranches, Rest, Next).


% --- Helpers for query/3 ---

% compile_query(+Query, -CompiledAtom, -Obligations)
% Compile Query via the query compiler; a query that does not compile is an
% error, not a failed branch.
compile_query(Query, CompiledAtom, Obligations) :-
    query_compiler:compile_query(Query, CompiledAtom, Obligations), !.
compile_query(Query, _, _) :-
    throw(error(query_compile_failed(Query), context(reduce_goal/6, _))).

% build_query_results(+F, +Rows, -Bag)
% Build result terms from Rows and unify with Bag.
% Each row is a value-list [V1, V2, ...]; the result term is F(V1, V2, ...).
user:build_query_results(F, Rows, Bag) :-
    maplist({F}/[Vs, T]>>(T =.. [F|Vs]), Rows, Bag).

% --- Packed interface for Python/Janus interop ---
%
% Janus cannot marshal compound Prolog terms to Python automatically.
% These predicates work entirely with atoms (which Janus maps to Python
% strings) and flat lists of atoms.
%
% The "packed" representation is a single atom string of the form:
%
%   adjourn_meta_pack(OrigGoal, State)
%
% Packing OrigGoal and State into ONE term (and hence one atom) ensures
% that identically-named variables in OrigGoal and the branch goals are
% treated as the SAME Prolog variable when parsed by read_term_from_atom/3.
% The Python side builds the packed atom from the user's original goal text,
% so OrigGoal always carries the user's variable names.

% step_packed(+PackedAtom, -EventAtom, -PackedOutAtom, -BindingFlatList)
%
%   PackedAtom      - atom encoding adjourn_meta_pack(OrigGoal, State)
%   EventAtom       - atom encoding the reduction event
%   PackedOutAtom   - atom encoding adjourn_meta_pack(OrigGoal, StateOut)
%   BindingFlatList - flat list [Name1, Val1, Name2, Val2, ...] (solution only)
step_packed(PackedAtom, EventAtom, PackedOutAtom, BindingFlatList) :-
    read_term_from_atom(PackedAtom,
                        adjourn_meta_pack(OrigGoal, State),
                        [variable_names(VarNames)]),
    step(State, Event, StateOut),
    term_to_atom(adjourn_meta_pack(OrigGoal, StateOut), PackedOutAtom),
    report_event(Event, OrigGoal-VarNames, EventAtom, BindingFlatList).

% report_event(+Event, +OrigGoal-VarNames, -EventAtom, -BindingFlatList)
% Translate an internal event into its external atom.  A solution is reported
% as the bare atom 'solution' (the Python side matches on that string), with
% the bindings recovered by unifying a copy of the top-level OrigGoal (which
% carries the user's variable names) with the solved branch's OrigGoal.  That
% unification cannot legitimately fail; if it does, step_packed/4 fails and
% the Python side raises.
report_event(done,             _,                 done,      []).
report_event(suspended(L),     _,                 EventAtom, []) :- term_to_atom(suspended(L), EventAtom).
report_event(checkpoint(L),    _,                 EventAtom, []) :- term_to_atom(checkpoint(L), EventAtom).
report_event(solution(Solved), OrigGoal-VarNames, solution,  BindingFlatList) :-
    copy_term(OrigGoal-VarNames, OGCopy-NamesCopy),
    OGCopy = Solved,
    extract_named_bindings_flat(NamesCopy, BindingFlatList).

% extract_named_bindings_flat(+VarNames, -FlatList)
% Return ground variables from VarNames as a flat [Name1, Val1, ...] list.
extract_named_bindings_flat(VarNames, FlatList) :-
    include([_N=V]>>(ground(V)), VarNames, BoundPairs),
    maplist([Name=Var, Name, ValAtom]>>(term_to_atom(Var, ValAtom)),
            BoundPairs, Names, Values),
    interleave_lists(Names, Values, FlatList).

% interleave_lists(+Xs, +Ys, -Zs): [X1,Y1,X2,Y2,...].
interleave_lists([], [], []).
interleave_lists([X|Xs], [Y|Ys], [X,Y|Zs]) :- interleave_lists(Xs, Ys, Zs).

% parse_packed_branches(+PackedAtom, -FlatGoalList)
%
% Parse a packed atom and return all branches as a flat list of atoms, with
% the atom 'branch_start' separating branches and bare 'barrier' entries.
% Immediately after each
% 'branch_start' marker comes that branch's OrigGoal atom, then its goals:
%   [branch_start, OrigGoal1, goal1, goal2, ...,
%    barrier, branch_start, OrigGoal2, goal3, ...]
%
% Returns [] for an empty state (done).
parse_packed_branches(PackedAtom, FlatGoalList) :-
    read_term_from_atom(PackedAtom,
                        adjourn_meta_pack(_, State),
                        []),
    State = state(Branches),
    maplist(branch_as_atoms, Branches, BranchAtomLists),
    flatten_with_markers(BranchAtomLists, FlatGoalList).

% branch_as_atoms(+branch(OrigGoal, Goals), -[OrigGoalAtom, GoalAtom...])
% The OrigGoal atom is emitted first so the Python side can peel it back off
% into the branch dict's "orig_goal" field.
branch_as_atoms(branch(OrigGoal, Goals), [OrigGoalAtom|GoalAtoms]) :-
    term_to_atom(OrigGoal, OrigGoalAtom),
    maplist(term_to_atom, Goals, GoalAtoms).
branch_as_atoms(barrier, barrier).

flatten_with_markers([barrier|Rest], [barrier|Flat]) :- !,
    flatten_with_markers(Rest, Flat).
flatten_with_markers([], []).
flatten_with_markers([Items|Rest], [branch_start|Flat]) :-
    append(Items, RestFlat, Flat),
    flatten_with_markers(Rest, RestFlat).
