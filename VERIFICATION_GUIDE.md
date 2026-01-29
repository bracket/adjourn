# Verification and Testing Guide

## Overview
This document provides a testing guide for the enhanced graph coloring demo that tracks and displays full interpreter state at each suspension point.

## Prerequisites
- SWI-Prolog 9.2.9+ installed
- Python 3.11+
- janus-swi Python package installed: `pip install janus-swi`

## Running the Demo

```bash
cd examples/graph_coloring
python demo.py
```

## Expected Output at Each Step

The demo should display state information at each suspension point:

### Step 1: Initial suspension (chose_a_red)
```
Step 1: Suspended at yield point
  Label: chose_a_red
  Interpreter State:
    Bindings: [binding(1,red),binding(2,_12345),binding(3,_12346),binding(4,_12347)]
    Remaining goals: [color(_G123),yield(chose_b(_G123)),...more goals...]

Continue? (yes/no) [yes]:
```

**Verification points:**
- [ ] Label "chose_a_red" is displayed
- [ ] Bindings show CA=red (binding(1,red))
- [ ] Other bindings show unbound variables (e.g., _12345)
- [ ] Remaining goals list is non-empty
- [ ] User is prompted to continue

### Step 2: After choosing color for B
```
Step 2: Suspended at yield point
  Label: chose_b(red)
  Interpreter State:
    Bindings: [binding(1,red),binding(2,red),binding(3,_12346),binding(4,_12347)]
    Remaining goals: [neq(red,red),...]

Continue? (yes/no) [yes]:
```

**Verification points:**
- [ ] Label shows "chose_b(red)" or similar color
- [ ] Bindings show CA=red, CB=red (if red was chosen)
- [ ] Remaining goals show constraint checking
- [ ] User is prompted to continue

### Subsequent Steps
The demo will continue through multiple steps:
- chose_c(Color): Choosing color for vertex C
- chose_d(Color): Choosing color for vertex D
- checked_constraints: All constraints verified

At each step verify:
- [ ] Bindings progressively show more bound variables
- [ ] Remaining goals list decreases in size
- [ ] State display is formatted clearly

### Final Step: Solution Found
```
Step N: Solution found!
  Coloring: a=red, b=green, c=blue, d=green

✓ Demo completed successfully
```

**Critical verification points:**
- [ ] All four colors are displayed: a, b, c, d
- [ ] Each color has an actual value (red, green, or blue)
- [ ] **NO placeholder '?' values are shown**
- [ ] The solution satisfies the adjacency constraint (adjacent vertices have different colors)
- [ ] Valid solution for 4-cycle: a-b-c-d-a with different colors on adjacent vertices

## Common Issues and Troubleshooting

### Issue: Bindings show only variables
If bindings always show unbound variables like `_12345`, this means:
- Variables are not being bound during computation
- State serialization is not preserving bindings
- Check that `init/2` creates the state correctly with the Goal term

### Issue: Solution shows '?' values
If the final solution displays placeholder values:
- The `extract_solution_from_state` function is not matching the goal correctly
- Check that the Goal pattern matches the actual goal structure
- Verify the state contains `state(Goal, Branches)` format

### Issue: State extraction fails
If "Warning: Failed to extract state components" appears:
- The Prolog queries in `extract_state_components` may have syntax errors
- Check that `extract_resolvents/2` and `extract_goal_bindings/2` are exported from toy_meta module
- Verify the state structure matches what the extraction predicates expect

## Manual Verification Checklist

### Before running the demo:
- [ ] SWI-Prolog is installed and in PATH
- [ ] janus-swi package is installed
- [ ] demo.py has no syntax errors
- [ ] toy_meta.pl has no syntax errors

### During demo execution:
- [ ] Demo loads Prolog files successfully
- [ ] Demo initializes interpreter successfully
- [ ] At first suspension point, state is displayed
- [ ] Bindings show CA=red (first variable bound)
- [ ] Remaining goals are displayed
- [ ] Can continue through all suspension points
- [ ] State evolves (more bindings, fewer goals)

### At completion:
- [ ] Solution is found
- [ ] All four colors (a, b, c, d) have actual values
- [ ] No '?' placeholders in solution
- [ ] Solution is valid (adjacent vertices have different colors)
- [ ] Demo exits cleanly with success message

## Example Valid Solutions

For a 4-cycle graph (a-b-c-d-a), any of these colorings are valid:
- a=red, b=green, c=red, d=green
- a=red, b=blue, c=red, d=blue
- a=red, b=green, c=blue, d=green
- ... (many other combinations)

The key constraint: adjacent vertices must have different colors:
- a ≠ b, b ≠ c, c ≠ d, d ≠ a

## Testing with Different Scenarios

### Test 1: Complete execution
Run the demo and answer "yes" to all prompts. Verify the solution is found and displayed correctly.

### Test 2: Early termination
Run the demo and answer "no" at some suspension point. Verify:
- Demo terminates gracefully
- Message "✓ User terminated execution" is shown
- Exit code is 0

### Test 3: State progression
At each suspension point, compare the state with the previous step:
- Number of bindings should stay the same or increase
- Number of remaining goals should decrease or stay the same
- Variables should not become "unbound" after being bound

## Code Changes Summary

### toy_meta.pl changes:
1. State structure: `state(Branches)` → `state(Goal, Branches)`
2. All predicates updated to handle new structure
3. New exports: `extract_resolvents/2`, `extract_goal_bindings/2`

### demo.py changes:
1. New function: `extract_state_components(state_str: str)`
2. New function: `pretty_print_state(state_components: Dict[str, Any])`
3. Modified: `extract_solution_from_state(state_str: str)` - now extracts real bindings
4. Modified: `run_demo()` - now displays state at each suspension point

## Success Criteria

The implementation is successful if:
1. ✅ State is displayed at every suspension point
2. ✅ Bindings are shown and progress through the computation
3. ✅ Remaining goals are shown and decrease over time
4. ✅ Solution displays actual color values (not placeholders)
5. ✅ All existing functionality still works (initialization, stepping, prompting)
