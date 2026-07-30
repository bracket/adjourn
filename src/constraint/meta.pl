% meta.pl
%
% Continuation-style meta-interpreter with explicit suspension/resumption.
% The interpreted program is given by rule/2 facts loaded separately.
%
% This module is the canonical meta-interpreter for the constraint package.
% It is located inside the Python package source tree so it is accessible
% via importlib.resources.

:- module(constraint_meta, [
    init/2,
    step/3,
    run/3,
    step_packed/4,
    parse_packed_branches/2,
    extract_bindings_str/4
]).

:- use_module(library(janus)).

% rule/2 is multifile in the user module so that any consulted ruleset can
% add rule/2 facts without module qualification.
:- multifile user:rule/2.

% --- State representation ---
% state(Branches)
% Branches is a list of branch(Goals), each Goals is a list representing
% the resolvent (the remaining goals to prove).

% init(+Goal, -State)
% Construct the initial interpreter state for a single goal.
init(Goal, state([branch([Goal])])).

% run/3 is a convenience alias for step/3.
run(State0, Event, State1) :- step(State0, Event, State1).

% step(+State0, -Event, -State1)
% Perform one reduction step.  Possible events:
%   done         — all branches exhausted
%   solution     — the first branch has an empty resolvent
%   suspended(L) — the first goal was yield(L); interpreter suspended

step(state([]), done, state([])) :- !.

% First branch has no remaining goals: emit a solution.
step(state([branch([])|Rest]), solution, state(Rest)) :- !.

% Otherwise, reduce one goal from the head of the current resolvent.
step(state([branch([G|Gs])|RestBranches]), Event, State1) :-
    reduce_goal(G, Gs, RestBranches, Event, State1).

% --- Goal reduction rules (continuation style) ---

% true: trivially succeeds; drop it and continue.
reduce_goal(true, Gs, Rest, Event, State1) :-
    step(state([branch(Gs)|Rest]), Event, State1).

% conjunction: flatten (A,B) into [A, B | Gs].
reduce_goal((A,B), Gs, Rest, Event, State1) :-
    step(state([branch([A,B|Gs])|Rest]), Event, State1).

% unification built-in: X = Y
reduce_goal((X=Y), Gs, Rest, Event, State1) :-
    X = Y,
    step(state([branch(Gs)|Rest]), Event, State1).

% cooperative suspension point:
% yield(Label) causes the interpreter to suspend and return
% suspended(Label).  The yield/1 goal has already been removed from
% the resolvent, so resuming from this state continues "after" it.
reduce_goal(yield(Label), Gs, Rest, suspended(Label), state([branch(Gs)|Rest])) :- !.

% foreign callout: invoke a registered Python function synchronously.
% py_call/2 is provided by library(janus) and calls into the Python runtime.
reduce_goal(foreign(Fn, In, Out), Gs, Rest, Event, State1) :-
    py_call(constraint_foreign:dispatch(Fn, In), Out),
    step(state([branch(Gs)|Rest]), Event, State1).

% general case: interpret via user:rule/2.
% Collect ALL matching rules for G, then create one branch per alternative.
% This makes choice points explicit and resumable.
% checkpoint(Label): persist the continuation and continue.
% Emits checkpoint(Label) event; the checkpoint goal is removed from the
% resolvent so resuming continues past it.
reduce_goal(checkpoint(Label), Gs, Rest, checkpoint(Label), state([branch(Gs)|Rest])) :- !.
reduce_goal(G, Gs, Rest, Event, State1) :-
    % Strip module qualification if present.
    (G = _Module:Goal -> UnqualifiedGoal = Goal ; UnqualifiedGoal = G),
    findall(branch(NewGoals),
            ( user:rule(UnqualifiedGoal, Body),
              body_to_goals(Body, BodyGoals),
              append(BodyGoals, Gs, NewGoals)
            ),
            NewBranches),
    % DFS order: explore the first alternative first, keep the rest for later.
    append(NewBranches, Rest, NextBranches),
    step(state(NextBranches), Event, State1).

% body_to_goals(+Body, -Goals)
% Convert a rule body into a flat goal list (resolvent segment).
body_to_goals(true, []) :- !.
body_to_goals((A,B), Goals) :- !,
    body_to_goals(A, GA),
    body_to_goals(B, GB),
    append(GA, GB, Goals).
body_to_goals(A, [A]).

% --- Packed interface for Python/Janus interop ---
%
% Janus cannot marshal compound Prolog terms to Python automatically.
% These predicates work entirely with atoms (which Janus maps to Python
% strings) and flat lists of atoms.
%
% The "packed" representation is a single atom string of the form:
%
%   constraint_meta_pack(OrigGoal, State)
%
% Packing OrigGoal and State into ONE term (and hence one atom) ensures
% that identically-named variables in OrigGoal and the branch goals are
% treated as the SAME Prolog variable when parsed by read_term_from_atom/3.
% This is the mechanism that allows variable binding extraction after a
% solution event.

% step_packed(+PackedAtom, -EventAtom, -PackedOutAtom, -BindingFlatList)
%
%   PackedAtom      — atom encoding constraint_meta_pack(OrigGoal, State)
%   EventAtom       — atom encoding the reduction event
%   PackedOutAtom   — atom encoding constraint_meta_pack(OrigGoal, StateOut)
%   BindingFlatList — flat list [Name1, Val1, Name2, Val2, ...] (solution only)
%
% BindingFlatList is populated only when EventAtom = 'solution'.
% Variable names reflect those present in the CURRENT PackedAtom; after the
% first serialisation round-trip they become internal names (_G123).
% Use extract_bindings_str/4 to recover original user-defined names.
step_packed(PackedAtom, EventAtom, PackedOutAtom, BindingFlatList) :-
    read_term_from_atom(PackedAtom,
                        constraint_meta_pack(OrigGoal, State),
                        [variable_names(VarNames)]),
    nb_setval(constraint_orig_goal, OrigGoal),
    step(State, Event, StateOut),
    term_to_atom(Event, EventAtom),
    term_to_atom(constraint_meta_pack(OrigGoal, StateOut), PackedOutAtom),
    (Event = solution ->
        extract_named_bindings_flat(VarNames, BindingFlatList)
    ;
        BindingFlatList = []
    ).

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
% Parse a packed atom and return all goals as a flat list of atoms, with
% the atom 'branch_start' separating branches.  Format:
%   [branch_start, goal1, goal2, ..., branch_start, goal3, ...]
%
% Returns [] for an empty state (done).
parse_packed_branches(PackedAtom, FlatGoalList) :-
    read_term_from_atom(PackedAtom,
                        constraint_meta_pack(_, State),
                        []),
    State = state(Branches),
    maplist(goals_as_atoms, Branches, BranchAtomLists),
    flatten_with_markers(BranchAtomLists, FlatGoalList).

goals_as_atoms(branch(Goals), GoalAtoms) :-
    maplist(term_to_atom, Goals, GoalAtoms).

flatten_with_markers([], []).
flatten_with_markers([Goals|Rest], [branch_start|Flat]) :-
    append(Goals, RestFlat, Flat),
    flatten_with_markers(Rest, RestFlat).

% extract_bindings_str(+OrigGoalStr, +PackedSolAtom, -VarNameList, -VarValueList)
%
% After a solution event, recover the original variable names and their
% bound values by unifying the original goal string with the bound goal
% in the packed solution atom.
%
% OrigGoalStr   — original goal as string, e.g. "color(X, Y)"
% PackedSolAtom — packed atom after solution,
%                 e.g. "constraint_meta_pack(color(red,blue),state([]))"
% VarNameList   — list of original variable name atoms, e.g. ['X', 'Y']
% VarValueList  — list of bound value atoms, e.g. ['red', 'blue']
%
% Both lists are [] when the original goal has no variables or the
% unification fails (common case due to findall variable copying).
extract_bindings_str(OrigGoalStr, PackedSolAtom, VarNameList, VarValueList) :-
    (   read_term_from_atom(OrigGoalStr, OrigGoal, [variable_names(VN)]),
        read_term_from_atom(PackedSolAtom,
                            constraint_meta_pack(SolGoal, _),
                            []),
        OrigGoal = SolGoal,
        include([_Name=Var]>>(ground(Var)), VN, BoundPairs),
        maplist([Name=Var, Name, ValAtom]>>(term_to_atom(Var, ValAtom)),
                BoundPairs, VarNameList, VarValueList)
    ->  true
    ;   VarNameList = [], VarValueList = []
    ).
