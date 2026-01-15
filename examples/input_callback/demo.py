"""Demonstration of Prolog-driven control flow with Python callbacks via Janus.

This example shows the inverse of the typical Python-calls-Prolog pattern.
Here, Prolog owns the main control flow and calls back to Python for user input.

This demonstrates:
1. Prolog as the control flow driver (owns the main loop)
2. Python callbacks invoked via py_call/2 from Prolog predicates
3. Bidirectional integration: Prolog -> Python -> Prolog
4. Clean handling of EOF (Ctrl-D) and empty input termination
5. List building and display logic living entirely in Prolog
"""

import sys
from pathlib import Path

import janus_swi as janus


def py_get_input() -> dict:
    """Get user input via Python's input() function.
    
    This function is called from Prolog as a foreign predicate.
    It reads a line from stdin and returns a structured response.
    
    Returns:
        A dictionary representing a Prolog compound term response(Content, Marker):
        - Content: The actual string entered by the user
        - Marker: 'ok' for normal input, 'eof' for EOF/Ctrl-D
        
        This allows the user to actually enter the string "eof" as input,
        while using the marker to detect when to terminate the loop.
    
    Note:
        This function is registered with Janus and called from Prolog.
        The dictionary is automatically converted to a Prolog compound term.
    """
    try:
        # Read input from user - no prompt, Prolog handles that
        user_input = input()
        # Return response(user_input, ok)
        return (user_input, 'ok')
    except EOFError:
        # User pressed Ctrl-D (EOF) - return response('', eof)
        return ('', 'eof')
    except KeyboardInterrupt:
        # User pressed Ctrl-C - treat as EOF
        print()  # Newline after ^C
        return ('', 'eof')


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
    1. Loads the Prolog file containing the main loop
    2. Invokes the Prolog main/0 goal to start the interactive loop
    3. Handles any errors that occur during execution
    
    The control flow is:
    - Python loads the Prolog file
    - Prolog file defines predicates that call back to Python via py_call/2
    - Python invokes the Prolog main/0 goal to start the loop
    - Prolog runs the main loop (input_loop/1)
    - Prolog calls back to Python for input (py_get_input/1 -> demo:py_get_input())
    - Prolog calls back to Python for output (py_print/1 -> demo:py_print(msg))
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
        result = janus.query_once(f"consult('{prolog_file}')")
        
        if not result or not result.get('truth', True):
            print(f"Error: Failed to load Prolog file: {prolog_file}", file=sys.stderr)
            sys.exit(1)
        
        print("✓ Prolog file loaded successfully")
        print()
        
        # Now invoke the main Prolog goal
        # This starts the interactive loop in Prolog, which will call back to Python
        # The Prolog predicates py_get_input/1 and py_print/1 use py_call/2 to
        # invoke the Python functions defined in this module
        print("Starting Prolog-driven interactive loop...")
        print()
        
        result = janus.query_once("main")
        
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
