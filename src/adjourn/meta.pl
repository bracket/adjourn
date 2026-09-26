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

% run/3 is a convenience alias for step/3.
run(State0, Event, State1) :- step(State0, Event, State1).

% step(+State0, -Event, -State1)
% Perform one reduction step.  Possible events:
%   done         — all branches exhausted
%   solution     — the first branch has an empty resolvent
%   suspended(L) — the first goal was yield(L); interpreter suspended

step(state([]), done, state([])) :- !.

% First branch has no remaining goals: emit a solution.  The branch's OrigGoal
% is now fully bound and is dropped along with the (empty) resolvent.
step(state([branch(SolvedOrigGoal, [])|Rest]), solution(SolvedOrigGoal), state(Rest)) :- !.

% Otherwise, reduce one goal from the head of the current resolvent, carrying
% this branch's OrigGoal so newly-created branches keep sharing its variables.
step(state([branch(OrigGoal, [G|Gs])|RestBranches]), Event, State1) :-
    reduce_goal(OrigGoal, G, Gs, RestBranches, Event, State1).

% --- Goal reduction rules (continuation style) ---

% true: trivially succeeds; drop it and continue.
reduce_goal(OrigGoal, true, Gs, Rest, Event, State1) :-
    step(state([branch(OrigGoal, Gs)|Rest]), Event, State1).

% conjunction: flatten (A,B) into [A, B | Gs].
reduce_goal(OrigGoal, (A,B), Gs, Rest, Event, State1) :-
    step(state([branch(OrigGoal, [A,B|Gs])|Rest]), Event, State1).

% unification built-in: X = Y
reduce_goal(OrigGoal, (X=Y), Gs, Rest, Event, State1) :-
    X = Y,
    step(state([branch(OrigGoal, Gs)|Rest]), Event, State1).

% cooperative suspension point:
% yield(Label) causes the interpreter to suspend and return
% suspended(Label).  The yield/1 goal has already been removed from
% the resolvent, so resuming from this state continues "after" it.
reduce_goal(OrigGoal, yield(Label), Gs, Rest, suspended(Label), state([branch(OrigGoal, Gs)|Rest])) :- !.

% foreign callout: invoke a registered Python function synchronously.
% py_call/2 is provided by library(janus) and calls into the Python runtime.
reduce_goal(OrigGoal, foreign(Fn, In, Out), Gs, Rest, Event, State1) :-
    py_call(adjourn_foreign:dispatch(Fn, In), Out),
    step(state([branch(OrigGoal, Gs)|Rest]), Event, State1).


% query/3: compile and reduce via foreign/3 callout.
% Placed before the general user:rule/2 dispatch clause.
reduce_goal(OrigGoal, query(Store:Template, Query, Bag), Gs, Rest, Event, State1) :-
    query_compiler:compile_query(query(Store:Template, Query, Bag), CompiledAtom, Obligations),
    term_to_atom(Obligations, ObligationsAtom),
    Template =.. [F|_],
    % Reduce foreign(mnestic_query, ...) through the existing foreign/3 path
    % by calling step on a state with the foreign goal.  The continuation
    % builds result terms from the returned rows then proceeds with Gs.
    step(state([branch(OrigGoal, [
        foreign(mnestic_query, [CompiledAtom, ObligationsAtom], Rows),
        build_query_results(F, Rows, Bag)
      | Gs]) | Rest]), Event, State1).

% general case: interpret via user:rule/2.
% Collect ALL matching rules for G, then create one branch per alternative.
% This makes choice points explicit and resumable.
% checkpoint(Label): persist the continuation and continue.
% Emits checkpoint(Label) event; the checkpoint goal is removed from the
% resolvent so resuming continues past it.
reduce_goal(OrigGoal, checkpoint(Label), Gs, Rest, checkpoint(Label), state([branch(OrigGoal, Gs)|Rest])) :- !.
reduce_goal(OrigGoal, G, Gs, Rest, Event, State1) :-
    % Strip module qualification if present.
    (G = _Module:Goal -> UnqualifiedGoal = Goal ; UnqualifiedGoal = G),
    % Test for a rule of this functor/arity using a fresh skeleton, NOT the
    % goal instance itself.  This distinguishes "defined predicate, but no
    % clause matches this instance" (an ordinary failure: the branch dies and
    % we backtrack) from "no such predicate at all" (an error, below).  It also
    % must not bind any variables of the goal, since they are shared with
    % OrigGoal and the continuation Gs.
    functor(UnqualifiedGoal, Functor, Arity),
    functor(Skeleton, Functor, Arity),
    ( \+ \+ user:rule(Skeleton, _) ->
        % One branch per matching rule.  When no clause matches this instance
        % NewBranches is [] and the branch simply drops out of the state.  findall/3 copies each template, which
        % is exactly what we want here: distinct alternatives must be able to
        % bind the goal's variables to distinct values.  We include OrigGoal
        % (and the head goal G) INSIDE the copied template as OGCopy/GCopy, so
        % each branch gets its own OrigGoal copy whose variables are shared,
        % through the head unification, with that branch's resolvent.  This is
        % what lets a solution recover the goal's bindings for that branch.
        findall(branch(OGCopy, NewGoals),
                ( copy_term(OrigGoal-G-Gs, OGCopy-GCopy-GsCopy),
                  user:rule(GCopy, Body),
                  body_to_goals(Body, BodyGoals),
                  append(BodyGoals, GsCopy, NewGoals)
                ),
                NewBranches),
        % DFS order: explore the first alternative first, keep the rest for later.
        append(NewBranches, Rest, NextBranches),
        step(state(NextBranches), Event, State1)
    ; predicate_property(user:UnqualifiedGoal, visible) ->
        ( once(user:UnqualifiedGoal) ->
            step(state([branch(OrigGoal, Gs)|Rest]), Event, State1)
        ; step(state(Rest), Event, State1)
        )
    ; throw(error(unknown_goal(UnqualifiedGoal), context(reduce_goal/6, G)))
    ).

% body_to_goals(+Body, -Goals)
% Convert a rule body into a flat goal list (resolvent segment).
body_to_goals(true, []) :- !.
body_to_goals((A,B), Goals) :- !,
    body_to_goals(A, GA),
    body_to_goals(B, GB),
    append(GA, GB, Goals).
body_to_goals(A, [A]).


% --- Helper for query/3 result construction ---

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
% This is the mechanism that allows variable binding extraction after a
% solution event.

% step_packed(+PackedAtom, -EventAtom, -PackedOutAtom, -BindingFlatList)
%
%   PackedAtom      — atom encoding adjourn_meta_pack(OrigGoal, State)
%   EventAtom       — atom encoding the reduction event
%   PackedOutAtom   — atom encoding adjourn_meta_pack(OrigGoal, StateOut)
%   BindingFlatList — flat list [Name1, Val1, Name2, Val2, ...] (solution only)
%
% BindingFlatList is populated only when EventAtom = 'solution'.
% Variable names reflect those present in the CURRENT PackedAtom; after the
% first serialisation round-trip they become internal names (_G123).
% Use extract_bindings_str/4 to recover original user-defined names.
step_packed(PackedAtom, EventAtom, PackedOutAtom, BindingFlatList) :-
    read_term_from_atom(PackedAtom,
                        adjourn_meta_pack(OrigGoal, State),
                        [variable_names(VarNames)]),
    nb_setval(adjourn_orig_goal, OrigGoal),
    step(State, Event, StateOut),
    term_to_atom(adjourn_meta_pack(OrigGoal, StateOut), PackedOutAtom),
    ( Event = solution(SolvedOrigGoal) ->
        % Normalise the external event atom to bare 'solution' (the Python side
        % matches on the string 'solution').
        EventAtom = solution,
        % Recover bindings by unifying the top-level OrigGoal (which still
        % carries the user's variable NAMES from VarNames) against the solved
        % branch's bound OrigGoal.  Copy first so we don't disturb anything.
        ( catch(( copy_term(OrigGoal-VarNames, OGCopy-VNCopy),
                  OGCopy = SolvedOrigGoal,
                  extract_named_bindings_flat(VNCopy, BindingFlatList)
                ), _, fail)
        -> true
        ;  BindingFlatList = []
        )
    ;
        term_to_atom(Event, EventAtom),
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

% extract_bindings_str(+OrigGoalStr, +PackedSolAtom, -VarNameList, -VarValueList)
%
% After a solution event, recover the original variable names and their
% bound values by unifying the original goal string with the bound goal
% in the packed solution atom.
%
% OrigGoalStr   — original goal as string, e.g. "color(X, Y)"
% PackedSolAtom — packed atom after solution,
%                 e.g. "adjourn_meta_pack(color(red,blue),state([]))"
% VarNameList   — list of original variable name atoms, e.g. ['X', 'Y']
% VarValueList  — list of bound value atoms, e.g. ['red', 'blue']
%
% Both lists are [] when the original goal has no variables or the
% unification fails (common case due to findall variable copying).
extract_bindings_str(OrigGoalStr, PackedSolAtom, VarNameList, VarValueList) :-
    (   read_term_from_atom(OrigGoalStr, OrigGoal, [variable_names(VN)]),
        read_term_from_atom(PackedSolAtom,
                            adjourn_meta_pack(SolGoal, _),
                            []),
        OrigGoal = SolGoal,
        include([_Name=Var]>>(ground(Var)), VN, BoundPairs),
        maplist([Name=Var, Name, ValAtom]>>(term_to_atom(Var, ValAtom)),
                BoundPairs, VarNameList, VarValueList)
    ->  true
    ;   VarNameList = [], VarValueList = []
    ).
