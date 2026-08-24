% qc_builtins.pl
%
% Translate v1 guard builtins into emitted-term functors.
% Only \=/2 is supported; everything else is a compile error.

:- module(qc_builtins, [ is_builtin/1, translate_builtin/2 ]).

% is_builtin(+Goal) — true iff Goal is a supported v1 standalone guard.
is_builtin(G) :-
    nonvar(G),
    G = (_ \= _).

% translate_builtin(+Goal, -Emitted) — translate Goal to its emitted form.
translate_builtin(X \= Y, '!='(X, Y)) :- !.
translate_builtin(Goal, _) :-
    throw(error(unsupported_builtin(Goal), _)).
