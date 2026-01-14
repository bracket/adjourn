"""Demonstration of Prolog-driven control flow with Python callbacks via Janus.

This example shows the inverse of the typical Python-calls-Prolog pattern.
Here, Prolog owns the main control flow and calls back to Python for user input.

This demonstrates:
1. Prolog as the control flow driver (owns the main loop)
2. Python callbacks registered as Janus foreign predicates
3. Bidirectional integration: Prolog -> Python -> Prolog
4. Clean handling of EOF (Ctrl-D) and empty input termination
5. List building and display logic living entirely in Prolog
"""

import sys
from pathlib import Path

from janus_swi import query_once


def py_get_input() -> str:
    """Get user input via Python's input() function.
    
    This function is called from Prolog as a foreign predicate.
    It reads a line from stdin and returns it as a string.
    
    Returns:
        The input string, or 'eof' atom on EOF (Ctrl-D)
    
    Note:
        This function is registered with Janus and called from Prolog.
        The return value is automatically converted to a Prolog term.
    """
    try:
        # Read input from user - no prompt, Prolog handles that
        user_input = input()
        return user_input
    except EOFError:
        # User pressed Ctrl-D (EOF) - return special atom
        return "eof"
    except KeyboardInterrupt:
        # User pressed Ctrl-C - treat as EOF
        print()  # Newline after ^C
        return "eof"


def py_print(message: str) -> None:
    """Print a message to stdout.
    
    This function is called from Prolog as a foreign predicate.
    It provides a way for Prolog to output messages via Python.
    
    Args:
        message: The message to print (string or Prolog term converted to string)
    
    Note:
        Using print() directly flushes output immediately, ensuring
        prompts appear before input() is called.
    """
    print(message, flush=True)


def main() -> None:
    """Main entry point for the Prolog-driven input callback demo.
    
    This function:
    1. Registers Python callback functions as Janus foreign predicates
    2. Loads the Prolog file containing the main loop
    3. Invokes the Prolog main/0 goal to start the interactive loop
    4. Handles any errors that occur during execution
    
    The control flow is:
    - Python registers callbacks and starts Prolog
    - Prolog runs the main loop (input_loop/1)
    - Prolog calls back to Python for input (py_get_input/1)
    - Prolog calls back to Python for output (py_print/1)
    - Prolog decides when to terminate
    - Control returns to Python when Prolog goal completes
    """
    try:
        # Get the path to the Prolog file in the same directory
        prolog_file = Path(__file__).parent / "input_loop.pl"
        
        # Add the current script directory to Python's sys.path so Prolog can import this module
        script_dir = Path(__file__).parent.resolve()
        if str(script_dir) not in sys.path:
            sys.path.insert(0, str(script_dir))
        
        # Load the Prolog file
        # Note: Using f-string is safe here because prolog_file is constructed
        # from __file__ (not user input). For user-supplied paths, validate first.
        print(f"Loading Prolog file: {prolog_file}")
        result = query_once(f"consult('{prolog_file}')")
        
        if not result or not result.get('truth', True):
            print(f"Error: Failed to load Prolog file: {prolog_file}", file=sys.stderr)
            sys.exit(1)
        
        print("✓ Prolog file loaded successfully")
        print()
        
        # Register Python callbacks with Janus
        # We define Prolog predicates that use py_call/2 to invoke our Python functions
        # For functions with no arguments: py_call(Module:Function, Result)
        # For functions with arguments: py_call(Module:Function(Args), Result)
        # For void functions (no return): use py_call(Module:Function(Args)) or py_call(Module:Function(Args), _)
        
        # Define the py_get_input/1 predicate in Prolog to call our Python function
        # py_get_input() takes no arguments and returns a string
        query_once("""
            assertz((py_get_input(Input) :-
                py_call(demo:py_get_input, Input)
            ))
        """)
        
        # Define the py_print/1 predicate in Prolog to call our Python function
        # py_print(message) takes a message argument and returns None
        query_once("""
            assertz((py_print(Message) :-
                py_call(demo:py_print(Message), _)
            ))
        """)
        
        # Now invoke the main Prolog goal
        # This starts the interactive loop in Prolog, which will call back to Python
        print("Starting Prolog-driven interactive loop...")
        print()
        
        result = query_once("main")
        
        # Check if the goal succeeded
        if result and result.get('truth', True):
            print()
            print("✓ Program completed successfully")
        else:
            print()
            print("⚠ Program terminated without success", file=sys.stderr)
            sys.exit(1)
            
    except FileNotFoundError as e:
        print(f"Error: Prolog file not found: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: An unexpected error occurred: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
