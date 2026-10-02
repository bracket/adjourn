# Graph Coloring Meta-Interpreter Demo

This demo implements a continuation-style Prolog meta-interpreter that solves a graph coloring constraint satisfaction problem with suspension and resumption capabilities.

## Overview

The demo demonstrates:
1. **Meta-interpreter pattern**: A Prolog interpreter written in Prolog that can suspend and resume computation
2. **Suspension points**: The computation yields control back to Python at designated points (`yield/1`)
3. **Interactive stepping**: Users can step through the computation one suspension point at a time
4. **CSP solving**: Solves a graph coloring problem on a 4-cycle graph (a-b-c-d-a)

## Files

- `demo.py`: Python driver program using Janus SWI for Prolog integration
- `toy_meta.pl`: Continuation-style meta-interpreter with suspension support
- `toy_graph_coloring.pl`: Graph coloring problem definition using `rule/2` facts
- `run_demo.sh`: Wrapper script that sets up environment variables for running the demo
- `spec/`: Reference specification files (unmodified originals)

## Requirements

- Python 3.11+
- SWI-Prolog 9.2.9+ (required for Janus Python integration) - [Download from swi-prolog.org](https://www.swi-prolog.org/Download.html)
- janus-swi Python package

## Running the Demo

Ensure SWI-Prolog is installed and available in your PATH, then run:

```bash
python3 demo.py
```

## How It Works

### The Problem

The demo colors a 4-cycle graph where vertices a, b, c, d are connected: a-b-c-d-a.
Each vertex must be assigned a color (red, green, or blue) such that adjacent vertices have different colors.

### The Meta-Interpreter

The meta-interpreter (`toy_meta.pl`) implements a continuation-style interpreter that:
- Maintains explicit branches for choice points
- Yields control at suspension points defined by `yield(Label)`
- Returns events: `suspended(Label)`, `solution`, or `done`
- Allows resumption by continuing with the returned state

### Execution Flow

1. **Initialization**: Python loads Prolog files and initializes the interpreter with the coloring goal
2. **Stepping**: At each step, the interpreter:
   - Processes one goal from the resolvent
   - Generates branches for choice points
   - Yields at suspension points
3. **User interaction**: Python prompts the user to continue or terminate
4. **Solution**: When a valid coloring is found, the demo displays success and exits

### Suspension Points

The demo suspends at these points:
- `chose_a_red`: Vertex a is fixed to red (symmetry breaking)
- `chose_b(Color)`: Choosing color for vertex b
- `chose_c(Color)`: Choosing color for vertex c
- `chose_d(Color)`: Choosing color for vertex d
- `checked_constraints`: All adjacency constraints verified

## Example Session

```
============================================================
Graph Coloring Meta-Interpreter Demo
============================================================

Loading: toy_meta.pl
Loading: toy_graph_coloring.pl
✓ All Prolog files loaded successfully

Initializing meta-interpreter with goal: coloring(CA, CB, CC, CD)
✓ Interpreter initialized

============================================================
Starting step-by-step execution
============================================================

Step 1: Suspended at yield point
  Label: chose_a_red

Continue? (yes/no) [yes]:

Step 2: Suspended at yield point
  Label: chose_b(red)

Continue? (yes/no) [yes]:

...

Step 20: Solution found!
  Coloring: a=red, b=green, c=blue, d=green

✓ Demo completed successfully
```

## Implementation Notes

### Janus Integration

The demo uses Janus SWI to integrate Python and Prolog:
- State is serialized as Prolog term strings and managed in Python
- Python parses state strings back to Prolog terms for each step
- Solution bindings are extracted using Prolog's dynamic database

### Variable Binding Extraction

When the meta-interpreter initializes, it stores the original goal with its variables in Prolog's dynamic database using `original_goal/1`. As the computation progresses, these variables get bound. When a solution is found, Python queries `original_goal/1` to extract the bound variable values.

### Module Qualification

The meta-interpreter handles module-qualified goals by stripping the module prefix when matching against `rule/2` facts.

### State Management

State is managed entirely in Python as serialized Prolog term strings. Each step:
1. Deserializes the state string to a Prolog term
2. Calls `step/3` to advance computation
3. Serializes the new state and event back to strings
4. Python processes the event and manages the state for the next iteration

## Purpose

This demo validates the core mechanism needed for the constraint project's goal-solving workflow, where:
- LLM agents need to inspect intermediate computation states
- Decisions about continuation are made based on current progress
- Complex constraint satisfaction problems require step-by-step validation
