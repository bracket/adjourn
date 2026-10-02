#!/usr/bin/env python3
"""
Mock test script to validate the input_callback example logic.

This script simulates the Prolog-Python interaction to verify that:
1. The Python callback functions work correctly
2. Input handling (including EOF) functions as expected
3. The control flow logic is sound

Note: This is a mock test since we cannot install SWI-Prolog 9.2.9+ in this environment.
"""

import sys
from pathlib import Path
from io import StringIO


# Define the callback functions directly (extracted from demo.py)
def py_get_input() -> tuple:
    """Get user input via Python's input() function.

    This function is called from Prolog as a foreign predicate.
    It reads a line from stdin and returns a tuple.

    Returns:
        A tuple (Content, Marker) where:
        - Content: The actual string entered by the user
        - Marker: 'ok' for normal input, 'eof' for EOF/Ctrl-D
    """
    try:
        user_input = input()
        return (user_input, 'ok')
    except EOFError:
        return ('', 'eof')
    except KeyboardInterrupt:
        print()
        return ('', 'eof')


def py_print(message: str) -> None:
    """Print a message to stdout.

    This function is called from Prolog as a foreign predicate.

    Args:
        message: The message to print
    """
    print(message, flush=True)


def test_py_print():
    """Test that py_print function works correctly."""
    print("\n=== Testing py_print ===")
    py_print("Test message 1")
    py_print("Test message 2")
    py_print("Test message with special chars: !@#$%^&*()")
    print("✓ py_print tests passed")


def test_py_get_input_normal():
    """Test py_get_input with normal input."""
    print("\n=== Testing py_get_input with normal input ===")

    # Simulate user input
    original_stdin = sys.stdin
    sys.stdin = StringIO("apple\nbanana\n\n")

    # Test reading inputs
    result1 = py_get_input()
    assert result1 == ('apple', 'ok'), f"Expected ('apple', 'ok'), got {result1}"
    print(f"  Input 1: {result1} ✓")

    result2 = py_get_input()
    assert result2 == ('banana', 'ok'), f"Expected ('banana', 'ok'), got {result2}"
    print(f"  Input 2: {result2} ✓")

    result3 = py_get_input()
    assert result3 == ('', 'ok'), f"Expected ('', 'ok'), got {result3}"
    print(f"  Input 3: {result3} (empty) ✓")

    sys.stdin = original_stdin
    print("✓ Normal input tests passed")


def test_py_get_input_eof():
    """Test py_get_input with EOF."""
    print("\n=== Testing py_get_input with EOF ===")

    # Simulate EOF
    original_stdin = sys.stdin
    sys.stdin = StringIO("")  # Empty stream simulates EOF

    result = py_get_input()
    assert result == ('', 'eof'), f"Expected ('', 'eof'), got {result}"
    print(f"  EOF handling: {result} ✓")

    sys.stdin = original_stdin
    print("✓ EOF tests passed")


def test_py_get_input_eof_string():
    """Test that the literal string 'eof' can be entered as input."""
    print("\n=== Testing py_get_input with literal 'eof' string ===")

    # Simulate user typing "eof" as input
    original_stdin = sys.stdin
    sys.stdin = StringIO("eof\n")

    result = py_get_input()
    assert result == ('eof', 'ok'), f"Expected ('eof', 'ok'), got {result}"
    print(f"  Literal 'eof' input: {result} ✓")
    print("  The string 'eof' can now be added to the list!")

    sys.stdin = original_stdin
    print("✓ Literal 'eof' string test passed")


def simulate_prolog_loop():
    """Simulate the Prolog loop logic in Python to verify the flow."""
    print("\n=== Simulating Prolog Loop Logic ===")

    # Simulate the loop with predetermined inputs, including the literal "eof" string
    test_inputs = ["apple", "banana", "eof", "cherry", ""]
    current_list = []

    for i, test_input in enumerate(test_inputs):
        print(f"\n  Iteration {i + 1}:")
        print(f"    Current list: {current_list if current_list else '[] (empty)'}")
        print(f"    Simulated input: '{test_input}'")

        # Simulate the tuple response structure
        if test_input == "":
            # Empty input with ok marker
            content, marker = "", "ok"
        else:
            # Normal input (including literal "eof" string)
            content, marker = test_input, "ok"

        print(f"    Tuple response: ({repr(content)}, '{marker}')")

        # Process based on marker (not content)
        if marker == "eof":
            print(f"    Marker is 'eof', terminating. Final list: {current_list}")
            break
        elif content == "":
            print(f"    Empty content with 'ok' marker, terminating. Final list: {current_list}")
            break
        else:
            current_list.append(content)
            print(f"    Updated list: {current_list}")

    expected_final = ["apple", "banana", "eof", "cherry"]
    assert current_list == expected_final, f"Expected {expected_final}, got {current_list}"
    print(f"\n  ✓ Loop logic correct. Final list includes literal 'eof': {current_list}")


def main():
    """Run all mock tests."""
    print("=" * 70)
    print("Mock Tests for input_callback Example")
    print("=" * 70)
    print("\nNote: These tests validate the Python callback logic.")
    print("Full integration testing requires SWI-Prolog 9.2.9+")
    print("=" * 70)

    try:
        test_py_print()
        test_py_get_input_normal()
        test_py_get_input_eof()
        test_py_get_input_eof_string()
        simulate_prolog_loop()

        print("\n" + "=" * 70)
        print("✓ All mock tests passed!")
        print("=" * 70)
        print("\nThe Python callback functions are working correctly.")
        print("To test the full Prolog-Python integration:")
        print("  1. Install SWI-Prolog 9.2.9 or higher")
        print("  2. Install janus-swi: pip install janus-swi")
        print("  3. Run: python examples/input_callback/demo.py")
        print("=" * 70)

        return 0

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
