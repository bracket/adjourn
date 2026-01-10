"""Tests for the constraint CLI."""

from pathlib import Path
from typing import List

import pytest
from click.testing import CliRunner

from constraint.cli.__main__ import main


@pytest.fixture
def runner() -> CliRunner:
    """Provide a Click CLI runner for testing."""
    return CliRunner()


class TestMainCommand:
    """Tests for the main CLI entry point."""

    def test_help_option(self, runner: CliRunner) -> None:
        """Test that --help displays help text."""
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Constraint checking system" in result.output
        assert "Commands:" in result.output

    def test_help_short_option(self, runner: CliRunner) -> None:
        """Test that -h displays help text."""
        result = runner.invoke(main, ["-h"])
        assert result.exit_code == 0
        assert "Constraint checking system" in result.output

    def test_version_option(self, runner: CliRunner) -> None:
        """Test that --version displays version information."""
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.0.0" in result.output

    def test_no_command_shows_help(self, runner: CliRunner) -> None:
        """Test that running without a command shows help."""
        result = runner.invoke(main, [])
        assert result.exit_code == 0
        assert "Commands:" in result.output


class TestCompleteCommand:
    """Tests for the complete subcommand."""

    def test_complete_help(self, runner: CliRunner) -> None:
        """Test that complete --help displays help text."""
        result = runner.invoke(main, ["complete", "--help"])
        assert result.exit_code == 0
        assert "Generate shell completion script" in result.output
        assert "--output" in result.output
        assert "--shell" in result.output

    def test_complete_stdout_bash(self, runner: CliRunner) -> None:
        """Test that complete generates bash completion to stdout."""
        result = runner.invoke(main, ["complete"])
        assert result.exit_code == 0
        assert "# Bash completion script" in result.output
        assert "Installation:" in result.output
        assert "_CONSTRAINT_COMPLETE=bash_source constraint" in result.output

    def test_complete_stdout_zsh(self, runner: CliRunner) -> None:
        """Test that complete generates zsh completion to stdout."""
        result = runner.invoke(main, ["complete", "--shell", "zsh"])
        assert result.exit_code == 0
        assert "# Zsh completion script" in result.output
        assert "#compdef constraint" in result.output
        assert "_CONSTRAINT_COMPLETE=zsh_source constraint" in result.output

    def test_complete_stdout_fish(self, runner: CliRunner) -> None:
        """Test that complete generates fish completion to stdout."""
        result = runner.invoke(main, ["complete", "--shell", "fish"])
        assert result.exit_code == 0
        assert "# Fish completion script" in result.output
        assert "_CONSTRAINT_COMPLETE=fish_source constraint" in result.output

    def test_complete_to_file(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test that complete writes to file with -o option."""
        output_file = tmp_path / "completion.sh"
        result = runner.invoke(main, ["complete", "-o", str(output_file)])
        assert result.exit_code == 0
        assert "Completion script written to:" in result.output
        assert output_file.exists()
        content = output_file.read_text()
        assert "# Bash completion script" in content
        assert "_CONSTRAINT_COMPLETE=bash_source constraint" in content

    def test_complete_to_file_creates_parent_dirs(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Test that complete creates parent directories when writing to file."""
        output_file = tmp_path / "nested" / "dir" / "completion.sh"
        result = runner.invoke(main, ["complete", "-o", str(output_file)])
        assert result.exit_code == 0
        assert output_file.exists()
        content = output_file.read_text()
        assert "# Bash completion script" in content

    def test_complete_file_with_zsh(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test that complete writes zsh completion to file."""
        output_file = tmp_path / "_constraint"
        result = runner.invoke(
            main, ["complete", "--shell", "zsh", "-o", str(output_file)]
        )
        assert result.exit_code == 0
        assert output_file.exists()
        content = output_file.read_text()
        assert "# Zsh completion script" in content
        assert "_CONSTRAINT_COMPLETE=zsh_source constraint" in content

    def test_complete_has_usage_header(self, runner: CliRunner) -> None:
        """Test that complete output includes usage instructions."""
        result = runner.invoke(main, ["complete"])
        assert result.exit_code == 0
        lines = result.output.split("\n")
        # Check that there are comment lines with instructions
        comment_lines = [line for line in lines if line.startswith("#")]
        assert len(comment_lines) > 0
        # Check for key instruction keywords
        full_output = result.output.lower()
        assert "installation:" in full_output
        assert "source" in full_output or "eval" in full_output


class TestCLIStructure:
    """Tests for the overall CLI structure."""

    def test_commands_are_registered(self, runner: CliRunner) -> None:
        """Test that expected commands are registered."""
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "complete" in result.output

    def test_invalid_command_shows_error(self, runner: CliRunner) -> None:
        """Test that invalid commands show appropriate error."""
        result = runner.invoke(main, ["invalid-command"])
        assert result.exit_code != 0
        assert "Error" in result.output or "No such command" in result.output
