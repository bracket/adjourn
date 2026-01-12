% list_member.pl
% Demonstrates basic list membership predicate for Janus integration example.

% member/2 - Check if Element is a member of List or enumerate elements.
%
% This is a standard Prolog predicate that can be used in two modes:
% 1. Check mode: member(+Element, +List) - succeeds if Element is in List
% 2. Generate mode: member(-Element, +List) - generates each element on backtracking
%
% Examples:
%   ?- member(2, [1, 2, 3]).
%   true.
%
%   ?- member(X, [1, 2, 3]).
%   X = 1 ;
%   X = 2 ;
%   X = 3.

% Base case: the head of the list is a member
member(Element, [Element|_]).

% Recursive case: check the tail of the list
member(Element, [_|Tail]) :-
    member(Element, Tail).
