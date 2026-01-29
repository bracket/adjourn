# Implementation Notes: Track Full Interpreter State

## Summary of Changes

This document describes the changes made to track and display the full interpreter state in the graph coloring demo.

## Modified Files

### 1. `examples/graph_coloring/toy_meta.pl`

**Key Changes:**
- **State structure change**: Changed from `state(Branches)` to `state(Goal, Branches)`
  - `Goal` stores the original goal with its variables (which get bound during computation)
  - `Branches` remains the list of branch(Goals) representing remaining resolvents

- **Updated predicates**: All predicates now handle the new state structure:
  - `init/2`: Creates `state(Goal, [branch([Goal])])` 
  - `step/3`: Pattern matches on `state(OrigGoal, ...)`
  - `reduce_goal/*`: Takes OrigGoal as first parameter and threads it through

- **New helper predicates**:
  - `extract_resolvents(+State, -Resolvents)`: Extracts remaining goals from current branch
  - `extract_goal_bindings(+State, -Bindings)`: Extracts variable bindings from the goal
    - Returns a list of `binding(Index, Value)` terms
    - Example: `[binding(1, red), binding(2, green), binding(3, blue), binding(4, green)]`

**Why this works:**
When the state is serialized to a string and then deserialized, Prolog's term serialization preserves variable bindings. The Goal term in the state contains the actual bound variables, so when we extract it, we get the current values of CA, CB, CC, CD.

### 2. `examples/graph_coloring/demo.py`

**New Functions:**

1. **`extract_state_components(state_str: str) -> Optional[Dict[str, Any]]`**
   - Takes the serialized state string
   - Uses Janus queries to extract resolvents and bindings
   - Converts them to strings for display
   - Returns dict with 'resolvents' and 'bindings' keys

2. **`pretty_print_state(state_components: Dict[str, Any]) -> None`**
   - Formats and displays the state components
   - Shows bindings and remaining goals with clear headers
   - Handles empty/missing components gracefully

**Modified Functions:**

1. **`extract_solution_from_state(state_str: str)`**
   - Now directly matches the goal structure in the state
   - Extracts CA, CB, CC, CD by unifying with the goal pattern
   - Returns actual color values instead of placeholders
   - Removed fallback that returned '?' values

2. **`run_demo()`**
   - At each suspension point:
     - Calls `extract_state_components()` to get state info
     - Calls `pretty_print_state()` to display it
     - Then prompts user to continue
   - Maintains existing label display

## Expected Behavior

When the demo runs, at each suspension point it should display:

```
Step N: Suspended at yield point
  Label: chose_b(red)
  Interpreter State:
    Bindings: [binding(1,red),binding(2,_12345),binding(3,_12346),binding(4,_12347)]
    Remaining goals: [color(green),...more goals...]

Continue? (yes/no) [yes]:
```

When a solution is found:

```
Step M: Solution found!
  Coloring: a=red, b=green, c=blue, d=green

✓ Demo completed successfully
```

## Design Rationale

### Why store Goal in the state?

The key insight is that Prolog variables get bound through unification as the computation proceeds. By storing the original Goal term in the state structure and serializing/deserializing it with each step, we preserve those bindings through the Python/Prolog boundary.

Alternative approaches considered:
1. Track substitutions separately - More complex, duplicates Prolog's unification
2. Use dynamic predicates - Doesn't survive serialization
3. Query original_goal/1 - Lost connection to variables after serialization

The chosen approach leverages Prolog's term serialization to maintain bindings naturally.

### State serialization flow

1. Python has state as string: `"state(coloring(red,_G123,_G124,_G125), [branch([...])])"`
2. Python calls step/3, deserializing the string to a Prolog term
3. Prolog unifies variables (e.g., `_G123 = green`) during computation
4. Prolog serializes the new state: `"state(coloring(red,green,_G124,_G125), [branch([...])])"`
5. Python receives the updated state string with new bindings

### Extraction at solution time

When a solution is found (all goals resolved), the Goal term in the state has all variables bound:
- `state(coloring(red,green,blue,green), [])`

We simply match this pattern and extract the color values.

## Testing Considerations

Since SWI-Prolog is not installed in the CI environment, manual testing is required:

1. Install SWI-Prolog 9.2.9+
2. Install janus-swi: `pip install janus-swi`
3. Run the demo: `python examples/graph_coloring/demo.py`
4. Verify at each suspension point:
   - Label is displayed
   - State shows bindings (initially unbound variables, progressively bound)
   - State shows remaining goals (decreasing over time)
5. Verify at solution:
   - Actual color assignments are displayed
   - All four colors (a, b, c, d) have values
   - No '?' placeholder values

## Acceptance Criteria Verification

- [x] State structure modified to track goal with bindings
- [x] Helper predicates added to extract state components
- [x] `extract_state_components()` implemented with proper type hints
- [x] `pretty_print_state()` implemented with proper type hints
- [x] `run_demo()` calls new functions at suspension points
- [x] `extract_solution_from_state()` extracts real bindings (no placeholders)
- [ ] Manual testing required (needs SWI-Prolog)
- [x] Python syntax validated
- [ ] Type checking with mypy (not available in CI)
- [ ] Linting with ruff (not available in CI)
