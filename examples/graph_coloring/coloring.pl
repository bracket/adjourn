% Graph coloring: color the vertices of a 4-cycle (a - b - c - d - a) with
% three colors so that adjacent vertices get different colors.

% Colors available to every vertex.
color(red).
color(green).
color(blue).

% The graph: a 4-cycle.
edge(a, b).
edge(b, c).
edge(c, d).
edge(d, a).

% Adjacency is symmetric.
adj(X, Y) :- edge(X, Y).
adj(X, Y) :- edge(Y, X).

% Adjacent vertices must have different colors.  \= is a host builtin.
ok_edge(X, Y, CX, CY) :- adj(X, Y), CX \= CY.

% Vertex a is always red (symmetry break).  Colors for b, c and d are chosen
% in order, and every choice is a point the search can backtrack to.  Each
% valid coloring suspends when a solution is found.
coloring(red, B, C, D) :-
    color(B), color(C), color(D),
    ok_edge(a, b, red, B),
    ok_edge(b, c, B, C),
    ok_edge(c, d, C, D),
    ok_edge(d, a, D, red).
