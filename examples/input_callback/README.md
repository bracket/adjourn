# Input Callback Example: Prolog-Driven Control Flow via Janus

## Overview

This example demonstrates **Prolog-driven control flow** with Python callbacks using Janus/SWI-Prolog. Unlike the `list_membership` example where Python calls Prolog, this example shows the **inverse pattern**: Prolog owns the main loop and calls back to Python for user input.

## What This Example Demonstrates

This example shows:

1. **Prolog as Control Flow Driver**: The main loop lives in Prolog, not Python
2. **Python Callbacks via Janus**: Prolog calls Python functions as foreign predicates
3. **Bidirectional Integration**: Data flows Prolog → Python → Prolog
4. **Interactive Input Handling**: Prolog uses Python's `input()` via callbacks
5. **Clean Termination**: Handles empty input and EOF (Ctrl-D) gracefully
6. **List Building in Prolog**: All list manipulation logic stays in Prolog

### Control Flow Comparison

**list_membership** (Python-driven):
```
Python main() → loads Prolog → queries Prolog → gets results → Python displays
```

**input_callback** (Prolog-driven):
```
Python main() → registers callbacks → invokes Prolog main/0 →
    Prolog loop → calls Python input() → Prolog processes →
    calls Python print() → Prolog recurses → ... → Prolog terminates →
    returns to Python
```

## Files

- **`input_loop.pl`**: Prolog source file defining the main loop and foreign predicate declarations
- **`demo.py`**: Python script that registers callbacks and invokes the Prolog main goal
- **`README.md`**: This documentation file

## Prerequisites

- Python 3.11 or higher
- SWI-Prolog 9.1 or higher installed on your system
- The `constraint` package installed with Janus support

## Installation

1. Ensure SWI-Prolog 9.1+ is installed:
   ```bash
   # On Ubuntu/Debian
   sudo apt-add-repository ppa:swi-prolog/stable
   sudo apt-get update
   sudo apt-get install swi-prolog
   
   # On macOS with Homebrew
   brew install swi-prolog
   
   # On Windows, download from: https://www.swi-prolog.org/Download.html
   ```

2. Install the constraint package with Janus:
   ```bash
   pip install -e /path/to/constraint
   ```
   
   This will automatically install the `janus-swi` dependency.

## Running the Example

From the project root directory:

```bash
python examples/input_callback/demo.py
```

Or from within the `examples/input_callback/` directory:

```bash
python demo.py
```

## Expected Interaction

```
Loading Prolog file: /path/to/examples/input_callback/input_loop.pl
✓ Prolog file loaded successfully

Starting Prolog-driven interactive loop...

Interactive List Builder (Prolog-driven with Python callbacks)
=============================================================
Enter values to add to the list. Press Enter on empty line or Ctrl-D to quit.

Current list: [] (empty)
Enter a value (or empty to quit): apple

Value added!
Current list (1 items): [apple]
Enter a value (or empty to quit): banana

Value added!
Current list (2 items): [apple, banana]
Enter a value (or empty to quit): cherry

Value added!
Current list (3 items): [apple, banana, cherry]
Enter a value (or empty to quit): 

Empty input received. Final list:
  [apple, banana, cherry]
Goodbye!

✓ Program completed successfully
```

## Termination Behavior

The program terminates gracefully in two ways:

1. **Empty Input**: Press Enter without typing anything
   - Displays "Empty input received"
   - Shows the final list
   - Exits cleanly

2. **EOF (Ctrl-D on Unix/Linux/Mac, Ctrl-Z on Windows)**:
   - Displays "EOF received"
   - Shows the final list
   - Exits cleanly

3. **Keyboard Interrupt (Ctrl-C)**:
   - Treated the same as EOF
   - Exits cleanly

All termination paths ensure:
- No uncaught exceptions
- Final list is displayed
- Clean exit code (0)

## How It Works

### The Prolog Side

The Prolog file (`input_loop.pl`) defines:

1. **Foreign Predicate Declarations**:
   ```prolog
   :- external(py_get_input/1, py_get_input).
   :- external(py_print/1, py_print).
   ```
   These declare that `py_get_input/1` and `py_print/1` are implemented in Python.

2. **Main Entry Point**:
   ```prolog
   main :-
       py_print('Interactive List Builder...'),
       input_loop([]).
   ```
   Starts the loop with an empty list.

3. **Interactive Loop**:
   ```prolog
   input_loop(CurrentList) :-
       % Display current state
       format_list_msg(CurrentList, ListMsg),
       py_print(ListMsg),
       
       % Get input from Python
       py_get_input(Input),
       
       % Process the input
       process_input(Input, CurrentList).
   ```

4. **Input Processing**:
   - `process_input(eof, List)`: Handles EOF
   - `process_input('', List)`: Handles empty input
   - `process_input(Input, List)`: Appends input and recurses

### The Python Side

The Python script (`demo.py`) does:

1. **Defines Callback Functions**:
   ```python
   def py_get_input() -> str:
       try:
           return input()
       except EOFError:
           return "eof"
   
   def py_print(message: str) -> None:
       print(message, flush=True)
   ```

2. **Registers Callbacks with Janus**:
   ```python
   # Load Prolog file
   query_once(f"consult('{prolog_file}')")
   
   # Register callbacks as Prolog predicates
   query_once("""
       assertz((py_get_input(Input) :-
           py_call(demo:py_get_input, Input)
       ))
   """)
   
   query_once("""
       assertz((py_print(Message) :-
           py_call(demo:py_print(Message), _)
       ))
   """)
   ```

3. **Invokes Prolog Main Goal**:
   ```python
   result = query_once("main")
   ```
   
   This transfers control to Prolog, which then calls back to Python as needed.

## Key Concepts

### Foreign Predicates in Janus

Janus allows Prolog to call Python functions as if they were native Prolog predicates. The integration works via:

- **Declaration in Prolog**: `:- external(predicate/arity, python_name)`
- **Registration from Python**: Using `py_call/2` or asserting wrapper predicates
- **Automatic Type Conversion**: Janus converts between Python and Prolog types:
  - Python `str` ↔ Prolog atom/string
  - Python `list` ↔ Prolog list
  - Python `dict` ↔ Prolog compound term
  - Python `None` ↔ Prolog unbound variable

### Control Flow Inversion

Unlike typical Python scripts that call library functions, this pattern inverts control:

- **Python's role**: Setup, registration, error handling
- **Prolog's role**: Main loop, decision logic, control flow
- **Benefits**: 
  - Leverage Prolog's declarative logic for complex control flow
  - Keep business logic in Prolog where it's more expressive
  - Use Python only for I/O and external integration

### Tail Recursion and Loop Efficiency

The Prolog loop uses tail recursion:
```prolog
input_loop(CurrentList) :-
    % ... display and get input ...
    process_input(Input, CurrentList).

process_input(Input, CurrentList) :-
    % ... append to list ...
    input_loop(NewList).  % Tail-recursive call
```

SWI-Prolog optimizes tail recursion, so this won't overflow the stack even with many iterations.

## Comparison with list_membership

| Aspect | list_membership | input_callback |
|--------|----------------|----------------|
| **Control Flow** | Python-driven | Prolog-driven |
| **Main Loop** | Python | Prolog |
| **Call Direction** | Python → Prolog | Prolog → Python |
| **Data Flow** | Python sends, Prolog returns | Prolog requests, Python provides |
| **Use Case** | Query Prolog knowledge base | Interactive Prolog application |
| **Complexity** | Simple queries | Complex control flow |

## Learning Path

To build upon this example:

1. **Modify the loop logic**: Add validation, filtering, or transformation in Prolog
2. **Add more callbacks**: Create additional Python functions for file I/O, networking, etc.
3. **Complex data structures**: Pass nested lists or dictionaries between Prolog and Python
4. **Error handling**: Extend error handling in both Prolog and Python
5. **State management**: Use Prolog's dynamic predicates to maintain state across calls

## Related Documentation

- [SWI-Prolog Documentation](https://www.swi-prolog.org/pldoc/doc_for?object=manual)
- [Janus Python Package](https://www.swi-prolog.org/pldoc/doc/_SWI_/library/janus.pl)
- [Constraint Project README](../../README.md)
- [List Membership Example](../list_membership/README.md) (for comparison)

## Troubleshooting

### "Module 'janus_swi' not found"
Ensure `janus-swi` is installed: `pip install janus-swi`

### "SWI-Prolog not found"
Install SWI-Prolog 9.1+ on your system (see Installation section above)

### "Foreign predicate not found"
Ensure the Prolog file is loaded successfully and the callbacks are registered before calling `main`.

### "Stack overflow" or runaway loop
This shouldn't happen with proper tail recursion optimization. If it does:
- Check that termination conditions (empty input/EOF) are working
- Verify the Prolog predicates use proper tail recursion
- Ensure the Python callbacks return the expected types

### Input prompt doesn't appear
The example uses `flush=True` in `py_print()` to ensure prompts appear immediately. If you still have issues, check your terminal buffering settings.

## Notes

- This example demonstrates a pattern useful for interactive Prolog applications
- The list building is intentionally simple to focus on the control flow pattern
- In production, consider adding input validation and error recovery
- The pattern scales to more complex applications: debuggers, interactive queries, games, etc.
