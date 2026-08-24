% qc_obligations.pl
%
% Provisional base/derived split over a query body, emitting base-relation
% obligations.

:- module(qc_obligations, [ base_obligations/2 ]).
:- use_module(qc_surface).
:- use_module(qc_builtins).
:- use_module(qc_derived).

% base_obligations(+QueryBodyGoals, -Obligations)
% Emit one base-relation obligation per distinct base relation referenced
% in the body, with the union of columns used across all occurrences.
base_obligations(Goals, Obligations) :-
    collect_base_goals(Goals, Pairs),
    merge_keys(Pairs, Merged),
    emit_obligations(Merged, Obligations).

% collect_base_goals(+Goals, -Pairs)
% Collect Functor-Keys pairs for each goal that is not builtin or derived.
collect_base_goals([], []).
collect_base_goals([Goal|Goals], Pairs) :-
    (   is_builtin(Goal)
    ->  collect_base_goals(Goals, Pairs)
    ;   is_derived(Goal)
    ->  collect_base_goals(Goals, Pairs)
    ;   classify_goal(Goal, Tag, Emitted),
        (   Tag = base
        ->  Emitted =.. [Functor, KVPairs],
            extract_keys(KVPairs, Keys)
        ;   Goal =.. [Functor|_],
            Keys = []
        ),
        Pairs = [Functor-Keys|Rest],
        collect_base_goals(Goals, Rest)
    ).

% extract_keys(+Pairs, -Keys)
% Extract keys from a list of Key-Value pairs.
extract_keys([], []).
extract_keys([K-_|Ps], [K|Ks]) :-
    extract_keys(Ps, Ks).

% merge_keys(+Pairs, -Merged)
% Group by functor and union the key lists.
merge_keys(Pairs, Merged) :-
    keysort(Pairs, Sorted),
    merge_sorted(Sorted, Merged).

% merge_sorted(+SortedPairs, -Merged)
merge_sorted([], []).
merge_sorted([F-Ks|Rest], [F-AllKeys|MergedRest]) :-
    same_functor_keys(F, Rest, ExtraKeyLists, Remaining),
    append([Ks|ExtraKeyLists], KeysFlat),
    sort(KeysFlat, AllKeys),
    merge_sorted(Remaining, MergedRest).

% same_functor_keys(+Functor, +Pairs, -ExtraKeyLists, -Remaining)
% Collect all key lists for the same functor from sorted pairs.
same_functor_keys(_, [], [], []).
same_functor_keys(F, [F-Ks|Rest], [Ks|More], Remaining) :-
    !,
    same_functor_keys(F, Rest, More, Remaining).
same_functor_keys(_, Remaining, [], Remaining).

% emit_obligations(+Merged, -Obligations)
% Convert Functor-UniqueKeys to Functor(Key1, Key2, ...) terms.
emit_obligations([], []).
emit_obligations([F-Ks|Rest], [Obl|Obls]) :-
    Obl =.. [F|Ks],
    emit_obligations(Rest, Obls).
