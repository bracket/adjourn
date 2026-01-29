"""Demonstration of meta-interpreter with suspension/resumption for graph coloring CSP.

This example demonstrates a continuation-style Prolog meta-interpreter that can
suspend and resume computation, allowing Python to inspect and control the
execution step-by-step. The demo solves a graph coloring constraint satisfaction
problem on a 4-cycle graph.

Key concepts demonstrated:
1. Meta-interpreter pattern: A Prolog interpreter written in Prolog
2. Suspension points: The computation yields control back to Python at designated points
3. Resumption: Python can choose to continue or terminate the computation
4. CSP solving: Graph coloring with adjacency constraints
5. State serialization: Python manages interpreter state via string serialization

The workflow:
- Python loads the meta-interpreter and graph coloring problem definitions
- Python initializes the interpreter with the coloring/4 goal
- The interpreter steps through the computation, yielding at suspension points
- Python serializes and manages the state as strings
- Python displays each suspension label and prompts user to continue
- When a solution is found, Python extracts and displays the color assignments
- The process continues until completion or user cancellation

This pattern is essential for the constraint project's goal-solving workflow,
where LLM agents need to inspect intermediate states and make decisions about
how to proceed with constraint validation.
"""

import sys
from pathlib import Path
from typing import Any, Dict, NoReturn, Optional

import janus_swi as janus  # type: ignore[import-untyped]


def load_prolog_files() -> bool:
    """Load the Prolog specification files for meta-interpreter and graph coloring.
    
    Returns:
        True if all files loaded successfully, False otherwise.
    
    The function loads:
    - toy_meta.pl: Continuation-style meta-interpreter with suspension support
    - toy_graph_coloring.pl: Graph coloring CSP problem definition
    """
    script_dir = Path(__file__).parent
    
    prolog_files = [
        script_dir / "toy_meta.pl",
        script_dir / "toy_graph_coloring.pl",
    ]
    
    for prolog_file in prolog_files:
        if not prolog_file.exists():
            print(f"Error: Prolog file not found: {prolog_file}", file=sys.stderr)
            return False
        
        print(f"Loading: {prolog_file.name}")
        try:
            result = janus.query_once(f"consult('{prolog_file}')")
            if not result or not result.get('truth', True):
                print(f"Error: Failed to load {prolog_file}", file=sys.stderr)
                return False
        except Exception as e:
            print(f"Error loading {prolog_file}: {e}", file=sys.stderr)
            return False
    
    print("✓ All Prolog files loaded successfully")
    return True


def initialize_interpreter() -> Optional[str]:
    """Initialize the meta-interpreter with the graph coloring goal.
    
    Returns:
        The initial interpreter state as a serialized string, or None if initialization failed.
    
    The goal is coloring(CA, CB, CC, CD) where CA, CB, CC, CD are the colors
    for vertices a, b, c, d in the 4-cycle graph.
    
    The state is serialized as a Prolog term string for Python to manage.
    """
    print("\nInitializing meta-interpreter with goal: coloring(CA, CB, CC, CD)")
    try:
        # Use toy_meta:init/2 to initialize the interpreter state
        # We'll serialize the state as a string for Python to manage
        # Use anonymous variables (_) to avoid issues with uninstantiated variables in Janus
        # Only bind StateStr to avoid Janus trying to serialize the complex State term
        result = janus.query_once(
            "toy_meta:init(toy_program_graph_coloring:coloring(_CA, _CB, _CC, _CD), _State), "
            "term_string(_State, StateStr)"
        )
        if result and result.get('truth', True):
            state_str = result.get('StateStr')
            print("✓ Interpreter initialized")
            return state_str
        else:
            print("Error: Failed to initialize interpreter", file=sys.stderr)
            return None
    except Exception as e:
        print(f"Error initializing interpreter: {e}", file=sys.stderr)
        return None


def prompt_user_continue() -> bool:
    """Prompt the user whether to continue execution.
    
    Returns:
        True if user wants to continue, False otherwise.
    
    Accepts case-insensitive yes/no input. Defaults to "yes" if empty input.
    Returns False on EOF or interrupt.
    """
    try:
        response = input("Continue? (yes/no) [yes]: ").strip().lower()
        # Default to "yes" if empty input
        if not response:
            return True
        return response in ('yes', 'y')
    except (EOFError, KeyboardInterrupt):
        print()  # Newline after ^C or ^D
        return False


def extract_state_components(state_str: str) -> Optional[Dict[str, Any]]:
    """Extract and deserialize the full interpreter state components.
    
    Args:
        state_str: Serialized state string from the meta-interpreter
    
    Returns:
        Dictionary with 'resolvents' and 'bindings' keys, or None if extraction fails.
        
    Uses Janus queries to extract:
    - resolvents: List of remaining goals to be proven
    - bindings: Dictionary of variable bindings (position -> value)
    """
    try:
        # Parse the state string back to a Prolog term and extract components
        result = janus.query_once(
            "term_string(_State, StateStr), "
            "toy_meta:extract_resolvents(_State, Resolvents), "
            "toy_meta:extract_goal_bindings(_State, Bindings), "
            "term_string(Resolvents, ResolventsStr), "
            "term_string(Bindings, BindingsStr)",
            {"StateStr": state_str}
        )
        
        if result and result.get('truth', True):
            return {
                'resolvents': result.get('ResolventsStr', '[]'),
                'bindings': result.get('BindingsStr', '[]')
            }
        return None
    except Exception as e:
        print(f"Warning: Failed to extract state components: {e}", file=sys.stderr)
        return None


def pretty_print_state(state_components: Dict[str, Any]) -> None:
    """Format and display the interpreter state in a human-readable format.
    
    Args:
        state_components: Dictionary containing 'resolvents' and 'bindings'
        
    Displays:
    - Remaining resolvents (goals to be proven)
    - Current variable substitutions/bindings
    """
    print("  Interpreter State:")
    
    # Display variable bindings
    bindings_str = state_components.get('bindings', '[]')
    if bindings_str and bindings_str != '[]':
        print(f"    Bindings: {bindings_str}")
    else:
        print("    Bindings: (none yet)")
    
    # Display remaining resolvents
    resolvents_str = state_components.get('resolvents', '[]')
    if resolvents_str and resolvents_str != '[]':
        print(f"    Remaining goals: {resolvents_str}")
    else:
        print("    Remaining goals: (none)")
    print()


def extract_solution_from_state(state_str: str) -> Optional[Dict[str, str]]:
    """Extract variable bindings from a solution state.
    
    Args:
        state_str: Serialized state string containing the solution
    
    Returns:
        Dictionary with variable bindings (CA, CB, CC, CD) or None if extraction fails.
    
    When a solution is found, the goal stored in the state contains the bound variables.
    We extract those bindings directly by matching the goal structure.
    """
    try:
        # Extract the goal directly from the state to get bound values
        # The goal is coloring(CA, CB, CC, CD) or more precisely
        # toy_program_graph_coloring:coloring(CA, CB, CC, CD)
        result = janus.query_once(
            "term_string(_State, StateStr), "
            "_State = state(Goal, _Branches), "
            # Match the goal structure and extract the color arguments
            "(Goal = toy_program_graph_coloring:coloring(CA, CB, CC, CD) ; Goal = coloring(CA, CB, CC, CD))",
            {"StateStr": state_str}
        )
        
        if result and result.get('truth', True):
            return {
                'CA': str(result.get('CA', '?')),
                'CB': str(result.get('CB', '?')),
                'CC': str(result.get('CC', '?')),
                'CD': str(result.get('CD', '?'))
            }
    except Exception as e:
        print(f"Warning: Failed to extract solution: {e}", file=sys.stderr)
    
    return None


def format_solution(bindings: Dict[str, str]) -> str:
    """Format the solution bindings as a readable color assignment.
    
    Args:
        bindings: Dictionary containing variable bindings (CA, CB, CC, CD)
    
    Returns:
        Formatted string like "a=red, b=green, c=blue, d=red"
    """
    names = ['a', 'b', 'c', 'd']
    vertex_vars = ['CA', 'CB', 'CC', 'CD']
    
    assignments = []
    for name, vertex_var in zip(names, vertex_vars):
        color = bindings.get(vertex_var, '?')
        assignments.append(f"{name}={color}")
    
    return ", ".join(assignments)


def run_demo() -> int:
    """Main demo loop: step through the meta-interpreter until completion.
    
    Returns:
        Exit code: 0 for success, 1 for error or user cancellation.
    
    The loop repeatedly calls step/3 with serialized state strings,
    handling three event types:
    - suspended(Label): A yield point where user can choose to continue
    - solution: A valid solution has been found
    - done: The computation has completed
    
    State is managed in Python as serialized Prolog term strings.
    """
    # Load Prolog files
    if not load_prolog_files():
        return 1
    
    # Initialize interpreter
    state_str = initialize_interpreter()
    if state_str is None:
        return 1
    
    print("\n" + "=" * 60)
    print("Starting step-by-step execution")
    print("=" * 60 + "\n")
    
    step_count = 0
    
    while True:
        step_count += 1
        
        try:
            # Call step/3 to advance the interpreter
            # Parse state string back to Prolog term, call step, serialize result
            # Use anonymous variables for complex terms to avoid Janus serialization issues
            result = janus.query_once(
                "term_string(_StateIn, StateInStr), "
                "toy_meta:step(_StateIn, _Event, _StateOut), "
                "term_string(_StateOut, StateOutStr), "
                "term_string(_Event, EventStr)",
                {"StateInStr": state_str}
            )
            
            if not result or not result.get('truth', True):
                print("\nError: step/3 failed", file=sys.stderr)
                return 1
            
            event_str = result.get('EventStr')
            new_state_str = result.get('StateOutStr')
            
            # Parse the event
            if 'suspended(' in event_str:
                # Extract label from suspended(Label)
                label_start = event_str.find('(') + 1
                label_end = event_str.rfind(')')
                label = event_str[label_start:label_end] if label_start > 0 and label_end > label_start else event_str
                
                print(f"Step {step_count}: Suspended at yield point")
                print(f"  Label: {label}")
                
                # Extract and display the full state
                state_components = extract_state_components(new_state_str)
                if state_components:
                    pretty_print_state(state_components)
                else:
                    print()
                
                if not prompt_user_continue():
                    print("\n✓ User terminated execution")
                    return 0
                
                # Continue with the new state
                state_str = new_state_str
                print()
            
            elif event_str == 'done':
                print(f"\nStep {step_count}: Computation complete (done)")
                print("✓ All solutions explored")
                return 0
            
            elif event_str == 'solution':
                print(f"\nStep {step_count}: Solution found!")
                
                # Extract and display the solution
                bindings = extract_solution_from_state(new_state_str)
                if bindings:
                    solution_str = format_solution(bindings)
                    print(f"  Coloring: {solution_str}")
                else:
                    print("  A valid coloring has been found for the 4-cycle graph!")
                
                print("\n✓ Demo completed successfully")
                return 0
            
            else:
                # Unknown event
                print(f"Step {step_count}: Event '{event_str}'")
                state_str = new_state_str
        
        except Exception as e:
            print(f"\nError during execution: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            return 1
        
        except Exception as e:
            print(f"\nError during execution: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            return 1


def main() -> NoReturn:
    """Entry point for the graph coloring meta-interpreter demo.
    
    Sets up the environment and runs the demo, exiting with appropriate status code.
    """
    try:
        print("=" * 60)
        print("Graph Coloring Meta-Interpreter Demo")
        print("=" * 60)
        print()
        print("This demo uses a meta-interpreter to solve a graph coloring")
        print("problem on a 4-cycle graph (a-b-c-d-a). The interpreter")
        print("suspends at each decision point, allowing you to step through")
        print("the computation interactively.")
        print()
        
        exit_code = run_demo()
        sys.exit(exit_code)
    
    except KeyboardInterrupt:
        print("\n\n✓ Demo interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nFatal error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
