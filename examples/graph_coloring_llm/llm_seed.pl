% Seed program for the LLM demo (demo.py).
%
% coloring/4 first suspends at implement_program, asking the LLM to define
% implementation/4.  When the driver resumes, clause 1 fails and clause 2
% calls implementation/4, which by then is defined by the LLM's rules.

coloring(_, _, _, _) :- implement_program, fail.
coloring(A, B, C, D) :- implementation(A, B, C, D).

implement_program :- yield(implement_program).
