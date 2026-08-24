% query_compiler.pl
%
% Top-level compiler entry point: compile a query/3 goal into an intermediate
% term (serialized) plus obligations.

:- module(query_compiler, [compile_query/3]).

:- use_module(qc_surface).      % classify_goal/3, keyed_goal/2
:- use_module(qc_builtins).     % is_builtin/1, translate_builtin/2
:- use_module(qc_projection).   % template_of/2, projection_cols/2
:- use_module(qc_derived).      % collect_derived/2, is_derived/1
:- use_module(qc_obligations).  % base_obligations/2

% compile_query(+QueryGoal, -CompiledTermAtom, -Obligations)
% Compile a query/3 goal into serialized intermediate term and obligations list.
compile_query(QueryGoal, CompiledTermAtom, [ProjCols|BaseObligs]) :-
    QueryGoal = query(Template, Body, _),
    body_goals(Body, GoalsList),
    map_goals(GoalsList, EmittedGoals),
    collect_derived(GoalsList, DerivedRules),
    template_of(Template, TemplateTerm),
    projection_cols(Template, ProjCols),
    base_obligations(GoalsList, BaseObligs),
    CompiledTerm = compiled_query(TemplateTerm, derived(DerivedRules), goals(EmittedGoals)),
    term_to_atom(CompiledTerm, CompiledTermAtom).

% body_goals(+Body, -Goals)
% Flatten a conjunction (A,B,...) into a list [A, B, ...].
body_goals((A, B), [A|Rest]) :-
    !,
    body_goals(B, Rest).
body_goals(Goal, [Goal]).

% map_goals(+Goals, -Emitted)
% Translate each body goal to its emitted form, in order.
map_goals([], []).
map_goals([Goal|Rest], [Emitted|EmittedRest]) :-
    map_goal(Goal, Emitted),
    map_goals(Rest, EmittedRest).

% map_goal(+Goal, -Emitted)
% Classify a single body goal: builtin, derived, or base (keyed surface).
map_goal(Goal, Emitted) :-
    is_builtin(Goal),
    !,
    translate_builtin(Goal, Emitted).
map_goal(Goal, Emitted) :-
    is_derived(Goal),
    !,
    Emitted = Goal.
map_goal(Goal, Emitted) :-
    classify_goal(Goal, _, Emitted).
