% qc_derived.pl
%
% Collect transitive closure of query_rule/2 derived relations reachable
% from a query body, emitting rule(Head, Body) term literals.

:- module(qc_derived, [ collect_derived/2, is_derived/1 ]).
:- use_module(qc_surface).

:- multifile user:query_rule/2.

% is_derived(+Goal)
% True iff Goal's functor/arity matches a query_rule/2 head.
is_derived(Goal) :-
    callable(Goal),
    functor(Goal, Name, Arity),
    user:query_rule(Head, _),
    functor(Head, Name, Arity).

% collect_derived(+QueryBodyGoals, -DerivedRules)
% Collect transitive closure of derived relations from body goals.
collect_derived(Goals, DerivedRules) :-
    collect_derived(Goals, [], DerivedRules).

% collect_derived(+Goals, +Seen, -DerivedRules)
% Seen is a list of Name/Arity already collected.
collect_derived([], _, []).
collect_derived([Goal|Goals], Seen, Rules) :-
    (   is_derived(Goal),
        functor(Goal, Name, Arity),
        \+ memberchk(Name/Arity, Seen)
    ->
        % Collect all clauses for this derived relation
        findall(rule(Head, ProcessedBody),
                (   functor(Head, Name, Arity),
                    user:query_rule(Head, Body),
                    process_body(Body, ProcessedBody)
                ),
                Clauses),
        % Find sub-goals from all clause bodies for transitive closure
        findall(SubGoal,
                (   functor(Head, Name, Arity),
                    user:query_rule(Head, Body),
                    member(SubGoal, Body)
                ),
                SubGoals),
        NewSeen = [Name/Arity|Seen],
        collect_derived(SubGoals, NewSeen, MoreRules),
        collect_derived(Goals, NewSeen, RestRules),
        append(Clauses, MoreRules, Rules0),
        append(Rules0, RestRules, Rules)
    ;
        collect_derived(Goals, Seen, Rules)
    ).

% process_body(+BodyGoals, -ProcessedGoals)
% Reassemble each body goal: base goals via qc_surface, derived unchanged.
process_body([], []).
process_body([Goal|Rest], [Processed|ProcessedRest]) :-
    classify_goal(Goal, _Tag, Processed),
    process_body(Rest, ProcessedRest).
