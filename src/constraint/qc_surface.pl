% qc_surface.pl
%
% Keyed base-surface parsing and goal classification.
% The SINGLE authority on interpreting a :/2 term as a key-value pair.

:- module(qc_surface, [ classify_goal/3, keyed_goal/2, normalize_pairs/2 ]).

% normalize_pairs(+SurfacePairs, -DashPairs)
% Map a list of Key: Value pairs (':'(K,V) terms) to Key-Value (-(K,V)) pairs,
% order preserved.
normalize_pairs([], []).
normalize_pairs([K:V|Rest], [K-V|DashRest]) :-
    !,
    normalize_pairs(Rest, DashRest).

% keyed_goal(+SurfaceGoal, -EmittedGoal)
% Reassemble a keyed base goal such as node(id: X, kind: K) into
% node([id-X, kind-K]).
keyed_goal(Goal, EmittedGoal) :-
    Goal =.. [Functor|Args],
    Args \== [],
    normalize_pairs(Args, DashPairs),
    EmittedGoal =.. [Functor, DashPairs].

% classify_goal(+Goal, -Tag, -Emitted)
% If Goal is a keyed base goal (compound whose arguments are all :/2 pairs),
% Tag = base and Emitted = reassembled keyed form; otherwise Tag = other.
classify_goal(Goal, base, Emitted) :-
    compound(Goal),
    Goal =.. [_|Args],
    Args \== [],
    maplist(is_keyed_pair, Args),
    !,
    keyed_goal(Goal, Emitted).
classify_goal(Goal, other, Goal).

% is_keyed_pair(+Term)
% True if Term is a concrete :/2 term (Key: Value), not a variable.
is_keyed_pair(Term) :-
    nonvar(Term),
    Term = _:_.
