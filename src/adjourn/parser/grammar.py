"""Lark grammar definition for Prolog parsing.

This module contains the Lark grammar string that defines the syntax for parsing
Prolog code including terms, clauses, operators, lists, and directives.

The grammar is based on the Plammar Prolog grammar library and supports standard
SWI-Prolog operators and syntax.
"""

# Lark grammar for Prolog
# Based on Plammar grammar with SWI-Prolog operator precedence
PROLOG_GRAMMAR = r"""
    // Top-level rules
    start: program
    program: item*
    item: clause | directive

    // Clauses and directives
    clause: clause_term "." -> fact
          | clause_term ":-" clause_body "." -> rule

    directive: ":-" clause_body "."

    // Clause head and body (at precedence below 1200 to avoid capturing :-)
    clause_term: term1100
    clause_body: term1200

    // Terms with operator precedence (1200 is max)
    term: term1200

    // Arguments (at precedence 999, below comma at 1000)
    arg_term: term900

    // Precedence 1200: :- (directive), --> (DCG)
    term1200: term1200 ":-" term1200 -> op_if
            | term1200 "-->" term1200 -> op_dcg
            | term1150

    // Precedence 1150: prefix operators (multifile, dynamic, etc.)
    term1150: "multifile" term1100 -> op_multifile
            | "dynamic" term1100 -> op_dynamic
            | "discontiguous" term1100 -> op_discontiguous
            | "volatile" term1100 -> op_volatile
            | "thread_local" term1100 -> op_thread_local
            | "initialization" term1100 -> op_initialization
            | "thread_initialization" term1100 -> op_thread_initialization
            | "module_transparent" term1100 -> op_module_transparent
            | "meta_predicate" term1100 -> op_meta_predicate
            | "public" term1100 -> op_public
            | "table" term1100 -> op_table
            | term1100

    // Precedence 1100: ; (disjunction)
    term1100: term1100 ";" term1050 -> op_semicolon
            | term1050

    // Precedence 1050: -> (if-then), *-> (soft cut)
    term1050: term1050 "->" term1000 -> op_if_then
            | term1050 "*->" term1000 -> op_soft_cut
            | term1000

    // Precedence 1000: , (conjunction)
    term1000: term900 "," term1000 -> op_comma
            | term900

    // Precedence 900: \+ (negation)
    term900: "\\+" term900 -> op_not
           | term700

    // Precedence 700: comparison operators
    term700: term700 "=" term600 -> op_unify
           | term700 "\\=" term600 -> op_not_unify
           | term700 "==" term600 -> op_eq
           | term700 "\\==" term600 -> op_neq
           | term700 "@<" term600 -> op_term_lt
           | term700 "@=<" term600 -> op_term_le
           | term700 "@>" term600 -> op_term_gt
           | term700 "@>=" term600 -> op_term_ge
           | term700 "=.." term600 -> op_univ
           | term700 "is" term600 -> op_is
           | term700 "=:=" term600 -> op_arith_eq
           | term700 "=\\=" term600 -> op_arith_neq
           | term700 "<" term600 -> op_lt
           | term700 "=<" term600 -> op_le
           | term700 ">" term600 -> op_gt
           | term700 ">=" term600 -> op_ge
           | term700 ">:<" term600 -> op_partial_unify
           | term700 ":<" term600 -> op_selectchk
           | term700 "=@=" term600 -> op_structural_eq
           | term700 "\\=@=" term600 -> op_structural_neq
           | term600

    // Precedence 600: : (module qualification)
    term600: term600 ":" term500 -> op_module_qual
           | term500

    // Precedence 500: arithmetic +, -, /\, \/
    term500: term500 "+" term400 -> op_plus
           | term500 "-" term400 -> op_minus
           | term500 "/\\" term400 -> op_bitwise_and
           | term500 "\\/" term400 -> op_bitwise_or
           | term400

    // Precedence 400: *, /, //, div, rem, mod, <<, >>, rdiv, xor
    term400: term400 "*" term200 -> op_multiply
           | term400 "/" term200 -> op_divide
           | term400 "//" term200 -> op_int_divide
           | term400 "div" term200 -> op_div
           | term400 "rem" term200 -> op_rem
           | term400 "mod" term200 -> op_mod
           | term400 "<<" term200 -> op_shift_left
           | term400 ">>" term200 -> op_shift_right
           | term400 "rdiv" term200 -> op_rational_div
           | term400 "xor" term200 -> op_xor
           | term200

    // Precedence 200: ** (power), ^ (power), unary +, -, \
    term200: term200 "**" primary -> op_power
           | term200 "^" primary -> op_caret
           | "+" term200 -> op_unary_plus
           | "-" term200 -> op_unary_minus
           | "\\" term200 -> op_bitwise_not
           | primary

    // Primary terms (atoms, variables, numbers, compounds, lists, parenthesized)
    primary: atom
           | variable
           | number
           | string
           | compound
           | list
           | "(" term ")"
           | "{" "}" -> empty_curly
           | "{" term "}" -> curly_term
           | "!" -> cut

    // Compound terms
    compound: atom "(" ")" -> compound_no_args
            | atom "(" arg_term ("," arg_term)* ")" -> compound_with_args

    // Lists
    list: "[" "]" -> empty_list
        | "[" list_contents "]"

    list_contents: arg_term -> list_single
                 | arg_term ("," arg_term)+ -> list_elements
                 | arg_term "|" arg_term -> list_with_tail
                 | arg_term ("," arg_term)+ "|" arg_term -> list_elements_with_tail

    // Atomic values
    atom: ATOM_LOWER | ATOM_QUOTED
    variable: VARIABLE
    number: INTEGER -> integer
          | FLOAT -> float
    string: STRING

    // Lexer rules
    ATOM_LOWER: /[a-z][a-zA-Z0-9_]*/
    ATOM_QUOTED: /'([^'\\]|\\.)*'/

    VARIABLE: /[A-Z_][a-zA-Z0-9_]*/

    INTEGER: /-?[0-9]+/
    FLOAT: /-?[0-9]+\.[0-9]+([eE][+-]?[0-9]+)?/

    STRING: /"([^"\\]|\\.)*"/

    // Comments and whitespace
    COMMENT: /%[^\n]*/
    BLOCK_COMMENT: /\/\*(.|\n)*?\*\//

    %import common.WS
    %ignore WS
    %ignore COMMENT
    %ignore BLOCK_COMMENT
"""
