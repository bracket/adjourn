# List Membership Example: Python-Prolog Integration via Janus

## Overview

This example demonstrates the fundamental concepts of Python-Prolog integration using Janus/SWI-Prolog. It shows how to:

- Load Prolog source files from Python
- Pass data structures (lists) from Python to Prolog
- Query Prolog predicates with variables
- Enumerate all solutions via backtracking
- Retrieve query results back in Python

## What This Example Demonstrates

The example implements a classic Prolog predicate `member/2` that checks list membership and can enumerate all elements of a list through backtracking. This demonstrates:

1. **Bidirectional Data Flow**: Python list → Prolog query → Python results
2. **Backtracking**: Using Prolog's ability to generate multiple solutions
3. **Two Query Modes**:
   - `query_once()`: Get a single solution (or check membership)
   - `query()`: Get all solutions via iteration (enumerate elements)

## Files

- **`list_member.pl`**: Prolog source file defining the `member/2` predicate
- **`demo.py`**: Python script demonstrating Janus integration
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
python examples/list_membership/demo.py
```

Or from within the `examples/list_membership/` directory:

```bash
python demo.py
```

## Expected Output

```
Python-Prolog Integration Demo: List Membership
==================================================
Original Python list: [10, 20, 30, 40, 50]

Loading Prolog file: /path/to/examples/list_membership/list_member.pl
✓ Prolog file loaded successfully

Enumerating list elements via Prolog:
--------------------------------------------------
  Element 1: 10
  Element 2: 20
  Element 3: 30
  Element 4: 40
  Element 5: 50
--------------------------------------------------
Total elements enumerated: 5

Testing membership check for value 30:
  ✓ 30 is a member of the list
Testing membership check for value 99:
  ✗ 99 is not a member of the list
```

## How It Works

### The Prolog Predicate

The `member/2` predicate is defined recursively:

```prolog
% Base case: the head of the list is a member
member(Element, [Element|_]).

% Recursive case: check the tail of the list
member(Element, [_|Tail]) :-
    member(Element, Tail).
```

This predicate works in two modes:
- **Check mode**: `member(30, [10, 20, 30])` → true/false
- **Generate mode**: `member(X, [10, 20, 30])` → X=10; X=20; X=30

### The Python Integration

The Python script uses Janus to interact with Prolog:

```python
from pathlib import Path
from janus_swi import query_once, query

# Get the path to the Prolog file
prolog_file = Path(__file__).parent / "list_member.pl"

# Load Prolog file
# Note: This uses string interpolation which is safe here since the path
# is derived from __file__. For user-supplied paths, validate/sanitize first.
query_once(f"consult('{prolog_file}')")

# Enumerate all elements
for solution in query("member(X, List)", {"List": [10, 20, 30]}):
    print(solution["X"])  # Prints: 10, 20, 30

# Check membership
result = query_once("member(Value, List)", {"Value": 30, "List": [10, 20, 30]})
# In Janus 1.5+, when all variables are bound, query_once returns:
#   - {'truth': True} if the query succeeds
#   - {'truth': False} if the query fails
if result and result.get('truth', True):
    print("30 is in the list")
```

## Key Concepts

### Janus Query Functions

- **`query_once(query_string, bindings={})`**: Executes a Prolog query and returns the first solution (or None). Use for membership checks or deterministic queries.
  - Returns a dictionary with variable bindings if the query has unbound variables
  - Returns `None` if the query fails completely
  - **Important (Janus 1.5+)**: When all variables are bound (e.g., membership checks), returns `{'truth': True}` on success or `{'truth': False}` on failure. Check with `result and result.get('truth', True)`.
  
- **`query(query_string, bindings={})`**: Returns an iterator over all solutions. Use for enumerating multiple results via backtracking.

### Variable Binding

Variables in Prolog queries are represented as:
- Uppercase names in the query string (e.g., `X`, `List`, `Element`)
- Dictionary keys in the bindings parameter
- Dictionary keys in the result

Example:
```python
# Query: "member(X, List)"
# Bindings: {"List": [1, 2, 3]}
# Results: {"X": 1}, {"X": 2}, {"X": 3}
```

## Learning Path

This example is intentionally minimal to illustrate core concepts. To build upon it:

1. **Modify the list**: Change the `numbers` list in `demo.py` to test with different data
2. **Add predicates**: Extend `list_member.pl` with additional list operations (length, append, etc.)
3. **Explore query modes**: Experiment with different variable bindings
4. **Complex data**: Try passing nested lists or other data structures

## Related Documentation

- [SWI-Prolog Documentation](https://www.swi-prolog.org/pldoc/doc_for?object=manual)
- [Janus Python Package](https://www.swi-prolog.org/pldoc/doc/_SWI_/library/janus.pl)
- [Constraint Project README](../../README.md)

## Troubleshooting

### "Module 'janus_swi' not found"
Ensure `janus-swi` is installed: `pip install janus-swi`

### "SWI-Prolog not found"
Install SWI-Prolog 9.1+ on your system (see Installation section above)

### "consult failed"
Check that the path to `list_member.pl` is correct. The script uses `Path(__file__).parent` to find it relative to `demo.py`.
