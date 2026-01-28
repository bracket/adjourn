% toy_program_graph_coloring.pl
%
% Interpreted program for toy_meta.pl, using rule/2.

:- module(toy_program_graph_coloring, [rule/2]).
:- multifile rule/2.

% --- domain ---
rule(color(red),   true).
rule(color(green), true).
rule(color(blue),  true).

% --- pure inequality as facts (no builtins) ---
rule(neq(red,green),   true).
rule(neq(green,red),   true).
rule(neq(red,blue),    true).
rule(neq(blue,red),    true).
rule(neq(green,blue),  true).
rule(neq(blue,green),  true).

% --- edges for a 4-cycle: a-b-c-d-a ---
rule(edge(a,b), true).
rule(edge(b,c), true).
rule(edge(c,d), true).
rule(edge(d,a), true).

% adjacency is symmetric
rule(adj(X,Y), edge(X,Y)).
rule(adj(X,Y), edge(Y,X)).

% constraint: adjacent nodes must have different colors
rule(ok_edge(X,Y,CX,CY), (adj(X,Y), neq(CX,CY))).

% --- the CSP itself ---
% symmetry break: CA fixed to red by head pattern coloring(red, ...)
rule(coloring(red, CB, CC, CD),
     ( yield(chose_a_red),
       color(CB), yield(chose_b(CB)),
       color(CC), yield(chose_c(CC)),
       color(CD), yield(chose_d(CD)),
       ok_edge(a,b,red,CB),
       ok_edge(b,c,CB,CC),
       ok_edge(c,d,CC,CD),
       ok_edge(d,a,CD,red),
       yield(checked_constraints)
     )).
