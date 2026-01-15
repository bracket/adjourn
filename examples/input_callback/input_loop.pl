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
% Mode: py_get_input(-Response)
%   Response: A compound term response(Content, Marker) where:
%     - Content is the actual string entered by the user
%     - Marker is 'ok' for normal input or 'eof' for EOF/Ctrl-D
%   This structure allows the user to enter the literal string "eof" as input
py_get_input(Response) :-
    py_call(demo:py_get_input(), Response).

% py_print/1 - Call Python to print a message
% This predicate uses py_call/2 to invoke the Python demo.py_print(message) function
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
% 4. On EOF marker: terminates gracefully
input_loop(CurrentList) :-
    % Show current list state
    format_list_msg(CurrentList, ListMsg),
    py_print(ListMsg),
    
    % Prompt for input via Python callback
    py_print('Enter a value (or empty to quit): '),
    
    % Get input from Python - this calls back to Python's input()
    (   py_get_input(Response)
    ->  % Input received successfully - extract content and marker
        Response = response(Content, Marker),
        process_input(Content, Marker, CurrentList)
    ;   % Input failed (should not happen normally)
        py_print('Error reading input. Exiting.'),
        fail
    ).

% process_input/3 - Handle the user's input
% Mode: process_input(+Content, +Marker, +CurrentList)
%   Content: The actual string entered by user
%   Marker: 'ok' for normal input, 'eof' for EOF/Ctrl-D
%   CurrentList: Current state of the list
process_input(_Content, eof, CurrentList) :-
    % EOF marker received (Ctrl-D) - clean termination
    !,
    py_print(''),
    py_print('EOF received. Final list:'),
    format_list_display(CurrentList, FinalMsg),
    py_print(FinalMsg),
    py_print('Goodbye!').

process_input('', ok, CurrentList) :-
    % Empty string with ok marker - clean termination
    !,
    py_print('Empty input received. Final list:'),
    format_list_display(CurrentList, FinalMsg),
    py_print(FinalMsg),
    py_print('Goodbye!').

process_input(Content, ok, CurrentList) :-
    % Non-empty input with ok marker - append to list and continue
    atom_string(ContentAtom, Content),  % Convert string to atom for cleaner display
    append(CurrentList, [ContentAtom], NewList),
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
