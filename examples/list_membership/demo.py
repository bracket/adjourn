"""Demonstration of Python-Prolog integration via Janus.

This example shows how to:
1. Initialize Janus and load a Prolog file
2. Pass data from Python to Prolog
3. Query Prolog predicates from Python
4. Enumerate all solutions via backtracking
5. Retrieve results back in Python
"""

from pathlib import Path
from typing import Any

from janus_swi import query_once, query


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
    
    # Demonstrate membership check
    test_value = 30
    print(f"Testing membership check for value {test_value}:")
    result = query_once("member(Value, List)", {"Value": test_value, "List": numbers})
    if result:
        print(f"  ✓ {test_value} is a member of the list")
    else:
        print(f"  ✗ {test_value} is not a member of the list")
    
    # Test with a value not in the list
    test_value = 99
    print(f"Testing membership check for value {test_value}:")
    result = query_once("member(Value, List)", {"Value": test_value, "List": numbers})
    if result:
        print(f"  ✓ {test_value} is a member of the list")
    else:
        print(f"  ✗ {test_value} is not a member of the list")


if __name__ == "__main__":
    main()
