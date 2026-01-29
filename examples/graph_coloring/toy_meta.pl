% toy_meta.pl
%
% Continuation-style meta-interpreter with explicit suspension/resumption.
% The interpreted program is given by rule/2 facts in a separate file.

:- module(toy_meta, [init/2, step/3, run/3, original_goal/1, extract_resolvents/2, extract_goal_bindings/2]).
:- multifile toy_program_graph_coloring:rule/2.

% Store the original goal for solution extraction
:- dynamic original_goal/1.

% --- State representation ---
% state(Goal, Branches)
% Goal is the original goal with its variables (which get bound during computation)
% Branches is a list of branch(Goals), each Goals is a list representing the resolvent.

init(Goal, state(Goal, [branch([Goal])])) :-
    retractall(original_goal(_)),
    assertz(original_goal(Goal)).

run(State0, Event, State1) :- step(State0, Event, State1).

step(state(OrigGoal, []), done, state(OrigGoal, [])) :- !.

% If the next branch has no remaining goals, we have found one solution.
% We emit solution and keep the remaining branches as the resumable state.
step(state(OrigGoal, [branch([])|Rest]), solution, state(OrigGoal, Rest)) :- !.

% Otherwise, reduce one goal from the head of the current resolvent.
step(state(OrigGoal, [branch([G|Gs])|RestBranches]), Event, State1) :-
    reduce_goal(OrigGoal, G, Gs, RestBranches, Event, State1).

% --- Goal reduction rules (continuation style) ---

% true: drop it
reduce_goal(OrigGoal, true, Gs, Rest, Event, State1) :-
    step(state(OrigGoal, [branch(Gs)|Rest]), Event, State1).

% conjunction: flatten (A,B) into A then B
reduce_goal(OrigGoal, (A,B), Gs, Rest, Event, State1) :-
    step(state(OrigGoal, [branch([A,B|Gs])|Rest]), Event, State1).

% cooperative suspension point
% yield(Label) causes the interpreter to stop and return suspended(Label),
% but with yield/1 removed from the resolvent so resuming continues "after" it.
reduce_goal(OrigGoal, yield(Label), Gs, Rest, suspended(Label), state(OrigGoal, [branch(Gs)|Rest])) :- !.

% general case: interpret via rule/2
% We collect ALL matching rules for G, then create one branch per alternative.
% This makes choice points explicit and resumable.
reduce_goal(OrigGoal, G, Gs, Rest, Event, State1) :-
    % Strip module qualification if present
    (G = _Module:Goal -> UnqualifiedGoal = Goal ; UnqualifiedGoal = G),
    findall(branch(NewGoals),
            ( toy_program_graph_coloring:rule(UnqualifiedGoal, Body),
              body_to_goals(Body, BodyGoals),
              append(BodyGoals, Gs, NewGoals)
            ),
            NewBranches),
    % DFS order: explore the first alternative immediately, keep the rest for later.
    append(NewBranches, Rest, NextBranches),
    step(state(OrigGoal, NextBranches), Event, State1).

% Convert a rule body into a goal list (resolvent segment).
body_to_goals(true, []) :- !.
body_to_goals((A,B), Goals) :- !,
    body_to_goals(A, GA),
    body_to_goals(B, GB),
    append(GA, GB, Goals).
body_to_goals(A, [A]).

% --- Helper predicates for state extraction ---

% extract_resolvents(+State, -Resolvents)
% Extract the list of remaining goals from the current branch
extract_resolvents(state(_, []), []).
extract_resolvents(state(_, [branch(Goals)|_]), Goals).

% extract_goal_bindings(+State, -Bindings)
% Extract variable bindings from the original goal in the state
% Returns a list of variable names and their bound values
extract_goal_bindings(state(Goal, _), Bindings) :-
    Goal =.. [_Functor|Args],
    collect_bound_args(Args, 1, Bindings).

% collect_bound_args(+Args, +Index, -Bindings)
% Collect bindings for each argument position
collect_bound_args([], _, []).
collect_bound_args([Arg|Rest], Index, [binding(Index, Arg)|RestBindings]) :-
    NextIndex is Index + 1,
    collect_bound_args(Rest, NextIndex, RestBindings).
