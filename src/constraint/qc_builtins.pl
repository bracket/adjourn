% qc_builtins.pl
%
% Translate v1 guard builtins into emitted-term functors.
% Only \=/2 is supported; everything else is a compile error.

:- module(qc_builtins, [ is_builtin/1, translate_builtin/2 ]).

% is_builtin(+Goal) — true iff Goal is a supported v1 standalone guard
%                     or an unsupported Prolog built-in.
is_builtin(G) :-
    nonvar(G),
    G = (_ \= _).
is_builtin(G) :-
    nonvar(G),
    compound(G),
    functor(G, Name, Arity),
    % Check if it's a Prolog built-in predicate or arithmetic operator
    (   predicate_property(system:Name/Arity, built_in)
    ;   predicate_property(system:Name/Arity, arithmetic_function)
    ;   is_operator(Name, Arity)
    ),
    % Exclude keyed surface syntax (Key: Value) which is handled by qc_surface
    \+ is_keyed_syntax(G).

% is_operator(+Name, +Arity)
% Explicit list of operators to recognize as builtins.
is_operator((>), 2).
is_operator((<), 2).
is_operator((>=), 2).
is_operator((=<), 2).
is_operator(is, 2).
is_operator((+), 2).
is_operator((-), 2).
is_operator((*), 2).
is_operator((//), 2).
is_operator(rem, 2).
is_operator(mod, 2).
is_operator(div, 2).
is_operator((**), 2).
is_operator((>>), 2).
is_operator((<<), 2).
is_operator(xor, 2).

% is_keyed_syntax(+Goal)
% True if Goal is a compound whose arguments are all Key:Value pairs.
is_keyed_syntax(G) :-
    compound(G),
    G =.. [_|Args],
    Args \== [],
    maplist(nonvar, Args),
    maplist([T]>>(T = _:_), Args).

% translate_builtin(+Goal, -Emitted) — translate Goal to its emitted form.
translate_builtin(X \= Y, '!='(X, Y)) :- !.
translate_builtin(Goal, _) :-
    throw(error(unsupported_builtin(Goal), _)).
