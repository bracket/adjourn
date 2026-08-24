% qc_projection.pl
%
% Derive the projection from a query Template.
% Template is Functor(Col1, Col2, ...); projection columns are its arguments.

:- module(qc_projection, [ template_of/2, projection_cols/2 ]).

% template_of(+Template, -TemplateTerm)
% Build template(Functor, [Cols...]) from the Template compound.
template_of(Template, template(Functor, Cols)) :-
    Template =.. [Functor|Cols].

% projection_cols(+Template, -Cols)
% Return the argument list of Template, in order.
projection_cols(Template, Cols) :-
    Template =.. [_|Cols].
