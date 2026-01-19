% toy_meta.pl
%
% Continuation-style meta-interpreter with explicit suspension/resumption.
% The interpreted program is given by rule/2 facts in a separate file.

:- module(toy_meta, [init/2, step/3, run/3, init_named/2, step_named/2]).
:- multifile toy_program_graph_coloring:rule/2.

% Store current state as a named global for janus compatibility
:- dynamic current_state/2.

% --- State representation ---
% state(Branches)
% Branches is a list of branch(Goals), each Goals is a list representing the resolvent.

init(Goal, state([branch([Goal])])).

% Initialize with a named state for easier janus integration
init_named(Name, Goal) :-
    init(Goal, State),
    retractall(current_state(Name, _)),
    assertz(current_state(Name, State)).

% Step with a named state, returning event as an atom for janus compatibility
step_named(Name, EventAtom) :-
    current_state(Name, State),
    step(State, Event, NewState),
    retractall(current_state(Name, _)),
    assertz(current_state(Name, NewState)),
    % Convert event to atom for janus
    (Event = suspended(Label) ->
        term_string(Label, LabelStr),
        atom_string(LabelAtom, LabelStr),
        atom_concat('suspended:', LabelAtom, EventAtom)
    ; Event = solution ->
        EventAtom = solution
    ; Event = done ->
        EventAtom = done
    ; term_string(Event, EventStr),
      atom_string(EventAtom, EventStr)
    ).

run(State0, Event, State1) :- step(State0, Event, State1).

step(state([]), done, state([])) :- !.

% If the next branch has no remaining goals, we have found one solution.
% We emit solution and keep the remaining branches as the resumable state.
step(state([branch([])|Rest]), solution, state(Rest)) :- !.

% Otherwise, reduce one goal from the head of the current resolvent.
step(state([branch([G|Gs])|RestBranches]), Event, State1) :-
    reduce_goal(G, Gs, RestBranches, Event, State1).

% --- Goal reduction rules (continuation style) ---

% true: drop it
reduce_goal(true, Gs, Rest, Event, State1) :-
    step(state([branch(Gs)|Rest]), Event, State1).

% conjunction: flatten (A,B) into A then B
reduce_goal((A,B), Gs, Rest, Event, State1) :-
    step(state([branch([A,B|Gs])|Rest]), Event, State1).

% cooperative suspension point
% yield(Label) causes the interpreter to stop and return suspended(Label),
% but with yield/1 removed from the resolvent so resuming continues "after" it.
reduce_goal(yield(Label), Gs, Rest, suspended(Label), state([branch(Gs)|Rest])) :- !.

% general case: interpret via rule/2
% We collect ALL matching rules for G, then create one branch per alternative.
% This makes choice points explicit and resumable.
reduce_goal(G, Gs, Rest, Event, State1) :-
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
    step(state(NextBranches), Event, State1).

% Convert a rule body into a goal list (resolvent segment).
body_to_goals(true, []) :- !.
body_to_goals((A,B), Goals) :- !,
    body_to_goals(A, GA),
    body_to_goals(B, GB),
    append(GA, GB, Goals).
body_to_goals(A, [A]).
