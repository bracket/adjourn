% input_loop.pl
% Demonstrates Prolog-driven control flow with Python callbacks via Janus.
%
% This example shows the inverse of the typical Python-calls-Prolog pattern:
% Here, Prolog owns the main loop and calls back to Python for user input.
%
% Key concepts demonstrated:
% 1. Prolog as the control flow driver
% 2. Foreign predicates declared for Python callbacks
% 3. Janus bi-directional integration (Prolog -> Python)
% 4. List building and display within Prolog
% 5. Clean termination on empty input or EOF

% py_get_input/1 - Call Python to get user input
% This predicate uses py_call/2 to invoke the Python demo.py_get_input() function
% Mode: py_get_input(-Input)
%   Input: String entered by user, or 'eof' atom on EOF/Ctrl-D
py_get_input(Input) :-
    py_call(demo:py_get_input(), Input).

% py_print/1 - Call Python to print a message
% This predicate uses py_call/1 to invoke the Python demo.py_print(message) function
% Mode: py_print(+Message)
%   Message: String or term to print
py_print(Message) :-
    py_call(demo:py_print(Message)).

% main/0 - Entry point for the interactive loop
% Starts the loop with an empty list and displays welcome message
main :-
    py_print('Interactive List Builder (Prolog-driven with Python callbacks)'),
    py_print('============================================================='),
    py_print('Enter values to add to the list. Press Enter on empty line or Ctrl-D to quit.'),
    py_print(''),
    input_loop([]).

% input_loop/1 - Main interactive loop that builds a list
% Mode: input_loop(+CurrentList)
%   CurrentList: The list accumulated so far
%
% This predicate:
% 1. Displays the current list state
% 2. Prompts for and reads user input via Python callback
% 3. On non-empty input: appends to list and recurses
% 4. On empty input or EOF: terminates gracefully
input_loop(CurrentList) :-
    % Show current list state
    format_list_msg(CurrentList, ListMsg),
    py_print(ListMsg),
    
    % Prompt for input via Python callback
    py_print('Enter a value (or empty to quit): '),
    
    % Get input from Python - this calls back to Python's input()
    (   py_get_input(Input)
    ->  % Input received successfully
        process_input(Input, CurrentList)
    ;   % Input failed (should not happen normally)
        py_print('Error reading input. Exiting.'),
        fail
    ).

% process_input/2 - Handle the user's input
% Mode: process_input(+Input, +CurrentList)
%   Input: The string entered by user or 'eof'
%   CurrentList: Current state of the list
process_input(eof, CurrentList) :-
    % EOF received (Ctrl-D) - clean termination
    !,
    py_print(''),
    py_print('EOF received. Final list:'),
    format_list_display(CurrentList, FinalMsg),
    py_print(FinalMsg),
    py_print('Goodbye!').

process_input('', CurrentList) :-
    % Empty string - clean termination
    !,
    py_print('Empty input received. Final list:'),
    format_list_display(CurrentList, FinalMsg),
    py_print(FinalMsg),
    py_print('Goodbye!').

process_input(Input, CurrentList) :-
    % Non-empty input - append to list and continue
    atom_string(InputAtom, Input),  % Convert string to atom for cleaner display
    append(CurrentList, [InputAtom], NewList),
    py_print(''),
    py_print('Value added!'),
    input_loop(NewList).  % Recurse with updated list

% format_list_msg/2 - Format the current list status message
% Mode: format_list_msg(+List, -Message)
format_list_msg([], Message) :-
    Message = 'Current list: [] (empty)'.
format_list_msg(List, Message) :-
    List \= [],
    length(List, Len),
    format(atom(Message), 'Current list (~w items): ~w', [Len, List]).

% format_list_display/2 - Format the final list display message
% Mode: format_list_display(+List, -Message)
format_list_display([], Message) :-
    Message = '  [] (empty)'.
format_list_display(List, Message) :-
    List \= [],
    format(atom(Message), '  ~w', [List]).
