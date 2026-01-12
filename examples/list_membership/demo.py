"""Demonstration of Python-Prolog integration via Janus.

This example shows how to:
1. Initialize Janus and load a Prolog file
2. Pass data from Python to Prolog
3. Query Prolog predicates from Python
4. Enumerate all solutions via backtracking
5. Retrieve results back in Python
"""

from pathlib import Path

from janus_swi import query_once, query


def check_membership(value: int, numbers: list[int]) -> None:
    """Check if a value is a member of the list and print the result.
    
    Args:
        value: The value to check for membership
        numbers: The list to check against
    """
    print(f"Testing membership check for value {value}:")
    result = query_once("member(Value, List)", {"Value": value, "List": numbers})
    # query_once returns None if the query fails, or a dict (possibly empty) if it succeeds
    # When all variables are bound, successful queries return {} (empty dict)
    # We must check 'is not None' rather than truthiness, since {} is falsy in Python
    if result is not None:
        print(f"  ✓ {value} is a member of the list")
    else:
        print(f"  ✗ {value} is not a member of the list")


def main() -> None:
    """Demonstrate Python-Prolog integration with list membership enumeration.
    
    This function:
    - Creates a Python list of numbers
    - Loads the Prolog file containing the member/2 predicate
    - Queries the predicate to enumerate all list elements
    - Prints each enumerated element to stdout
    """
    # Define a Python list of numbers
    numbers = [10, 20, 30, 40, 50]
    
    print("Python-Prolog Integration Demo: List Membership")
    print("=" * 50)
    print(f"Original Python list: {numbers}")
    print()
    
    # Get the path to the Prolog file in the same directory as this script
    prolog_file = Path(__file__).parent / "list_member.pl"
    
    # Load the Prolog file
    # The consult/1 predicate loads Prolog source files
    # Note: Using f-string here is safe because:
    #   1. prolog_file is constructed from __file__ (not user input)
    #   2. Path objects from pathlib normalize paths securely
    #   3. consult/1 requires a string path and doesn't support parameter binding
    # In production code with user-supplied paths, validate/sanitize paths first.
    print(f"Loading Prolog file: {prolog_file}")
    query_once(f"consult('{prolog_file}')")
    print("✓ Prolog file loaded successfully")
    print()
    
    # Query the member/2 predicate to enumerate all elements
    # The query "member(X, List)" will generate each element on backtracking
    print("Enumerating list elements via Prolog:")
    print("-" * 50)
    
    # Use query() to get all solutions (iterator that backtracks)
    element_count = 0
    for solution in query("member(X, List)", {"List": numbers}):
        element_count += 1
        element = solution["X"]
        print(f"  Element {element_count}: {element}")
    
    print("-" * 50)
    print(f"Total elements enumerated: {element_count}")
    print()
    
    # Demonstrate membership checks
    check_membership(30, numbers)
    check_membership(99, numbers)


if __name__ == "__main__":
    main()
