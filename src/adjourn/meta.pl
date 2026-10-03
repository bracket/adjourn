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
% Branches is a list of branch(OrigGoal, Goals).  Goals is the resolvent
% (the remaining goals to prove) for this branch.  OrigGoal is this branch's
% OWN copy of the original goal term; its variables are shared with the goals
% in this branch's resolvent, so bindings established while reducing the
% resolvent are reflected in OrigGoal.  Carrying OrigGoal per-branch (rather
% than once globally) is what lets distinct branches bind the goal's variables
% to distinct values, and lets those bindings survive serialization.

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

% conjunction: flatten (A,B) into [A, B | Gs].
reduce_goal(OrigGoal, (A,B), Gs, Rest, Event, State1) :- !,
    step(state([branch(OrigGoal, [A,B|Gs])|Rest]), Event, State1).

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
    rule_branches(Goal, OrigGoal, Gs, NewBranches),
    % DFS order: explore the first alternative first, keep the rest for later.
    append(NewBranches, Rest, Next).
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

% rule_branches(+Goal, +OrigGoal, +Gs, -Branches)
% One branch per rule whose head matches Goal.  When none match, Branches is
% [] and the current branch simply drops out of the state.  findall/3 copies
% each template, which is exactly what we want: distinct alternatives must be
% able to bind the goal's variables to distinct values.  OrigGoal (and Goal)
% are copied INSIDE the template as OGCopy/GoalCopy, so each branch gets its
% own OrigGoal copy whose variables are shared, through the head unification,
% with that branch's resolvent.  This is what lets a solution recover the
% goal's bindings for that branch.
rule_branches(Goal, OrigGoal, Gs, Branches) :-
    findall(branch(OGCopy, NewGoals),
            ( copy_term(OrigGoal-Goal-Gs, OGCopy-GoalCopy-GsCopy),
              user:rule(GoalCopy, Body),
              body_to_goals(Body, BodyGoals),
              append(BodyGoals, GsCopy, NewGoals)
            ),
            Branches).

% branch_survives(+Test, +Branch, +Rest, -Next)
% If Test succeeds (first solution only), Branch stays at the front;
% otherwise the branch dies and resolution continues with Rest.
branch_survives(Test, Branch, Rest, [Branch|Rest]) :- call(Test), !.
branch_survives(_,    _,      Rest, Rest).

% body_to_goals(+Body, -Goals)
% Convert a rule body into a flat goal list (resolvent segment).  An unbound
% body is kept as a single goal (so reducing it raises an instantiation
% error) rather than unifying with the true/0 or (,)/2 clause heads.
body_to_goals(Body, [Body]) :- var(Body), !.
body_to_goals(true, []) :- !.
body_to_goals((A,B), Goals) :- !,
    body_to_goals(A, GA),
    body_to_goals(B, GB),
    append(GA, GB, Goals).
body_to_goals(A, [A]).


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
% the atom 'branch_start' separating branches.  Immediately after each
% 'branch_start' marker comes that branch's OrigGoal atom, then its goals:
%   [branch_start, OrigGoal1, goal1, goal2, ...,
%    branch_start, OrigGoal2, goal3, ...]
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

flatten_with_markers([], []).
flatten_with_markers([Items|Rest], [branch_start|Flat]) :-
    append(Items, RestFlat, Flat),
    flatten_with_markers(Rest, RestFlat).
