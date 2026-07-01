"""Tests for the constraint CLI."""

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from constraint.cli.__main__ import main
from constraint.store import AggregateRuleSetStore, FileRuleSetStore

NONEMPTY_RULESET = "rule(test_fixture_placeholder, true).\n"


@pytest.fixture
def runner() -> CliRunner:
    """Provide a Click CLI runner for testing."""
    return CliRunner()


def _write_config(
    tmp_path: Path,
    rules: dict[str, str],
    *,
    aliases: dict[str, str] | None = None,
    store_names: dict[str, str] | None = None,
    prolog_modes: dict[str, str] | None = None,
) -> Path:
    """Create rules files plus a matching config file."""
    config_dir = tmp_path / ".constraint"
    rules_dir = tmp_path / "rules"
    config_dir.mkdir()
    rules_dir.mkdir()

    stores: list[dict[str, str]] = []
    computed_aliases: dict[str, str] = {}
    for name, content in rules.items():
        rules_path = rules_dir / f"{name}.pl"
        rules_path.write_text(content)
        prolog_mode = prolog_modes.get(name, "constraint") if prolog_modes else "constraint"
        store = FileRuleSetStore(rules_path, prolog=prolog_mode)
        ruleset_hash = store.known_rulesets()[0]
        store_config = {"type": "file", "path": str(Path("rules") / rules_path.name)}
        if store_names is not None and name in store_names:
            store_config["name"] = store_names[name]
        store_config["prolog"] = prolog_mode
        stores.append(store_config)
        computed_aliases[name] = ruleset_hash

    config_path = config_dir / "config.yaml"
    if aliases is None:
        aliases = computed_aliases
    config_path.write_text(yaml.safe_dump({"stores": stores, "aliases": aliases}))
    return config_path


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
        assert "store" in result.output

    def test_invalid_command_shows_error(self, runner: CliRunner) -> None:
        """Test that invalid commands show appropriate error."""
        result = runner.invoke(main, ["invalid-command"])
        assert result.exit_code != 0
        assert "Error" in result.output or "No such command" in result.output


class TestInitCommand:
    """Tests for the ``init`` subcommand."""

    def test_init_help(self, runner: CliRunner) -> None:
        """init --help should display usage information."""
        result = runner.invoke(main, ["init", "--help"])
        assert result.exit_code == 0
        assert "QUERY" in result.output or "query" in result.output.lower()

    def test_init_creates_state_file(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """init should create a JSON state file with status 'running'."""
        state_file = tmp_path / "state.json"
        config_path = _write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        result = runner.invoke(
            main,
            ["init", "true", str(state_file), "--ruleset", "test_rules", "--config", str(config_path)],
        )
        assert result.exit_code == 0, result.output
        assert state_file.exists()
        state = json.loads(state_file.read_text())
        assert state["status"] == "running"
        assert state["version"] == 0
        assert "ruleset_hash" in state

    def test_init_preserves_original_goal(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """The initial state file must preserve the original goal string."""
        goal = "color(X, Y)"
        state_file = tmp_path / "state.json"
        config_path = _write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        runner.invoke(
            main,
            ["init", goal, str(state_file), "--ruleset", "test_rules", "--config", str(config_path)],
        )
        state = json.loads(state_file.read_text())
        assert state["original_goal"] == goal

    def test_init_has_single_branch(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """The initial state must have exactly one branch containing the goal."""
        goal = "foo(bar)"
        state_file = tmp_path / "state.json"
        config_path = _write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        runner.invoke(
            main,
            ["init", goal, str(state_file), "--ruleset", "test_rules", "--config", str(config_path)],
        )
        state = json.loads(state_file.read_text())
        assert len(state["branches"]) == 1
        assert state["branches"][0]["goals"] == [goal]

    def test_init_creates_parent_dirs(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """init should create parent directories if they don't exist."""
        state_file = tmp_path / "sub" / "dir" / "state.json"
        config_path = _write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        result = runner.invoke(
            main,
            ["init", "true", str(state_file), "--ruleset", "test_rules", "--config", str(config_path)],
        )
        assert result.exit_code == 0, result.output
        assert state_file.exists()

    def test_init_resolves_store_name(self, runner: CliRunner, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        config_path = _write_config(
            tmp_path,
            {"test_rules": NONEMPTY_RULESET},
            aliases={},
            store_names={"test_rules": "named-rules"},
        )

        result = runner.invoke(
            main,
            [
                "init",
                "true",
                str(state_file),
                "--ruleset",
                "named-rules",
                "--config",
                str(config_path),
            ],
        )

        assert result.exit_code == 0, result.output
        state = json.loads(state_file.read_text())
        ruleset_hash = FileRuleSetStore(tmp_path / "rules" / "test_rules.pl").known_rulesets()[0]
        assert state["ruleset_hash"] == ruleset_hash

    def test_init_resolves_first_system_alias(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        state_file = tmp_path / "state.json"
        config_path = _write_config(
            tmp_path,
            {
                "first_rules": "p(a).\n",
                "second_rules": "q(b).\n",
            },
            aliases={},
        )

        result = runner.invoke(
            main,
            [
                "init",
                "true",
                str(state_file),
                "--ruleset",
                "@first",
                "--config",
                str(config_path),
            ],
        )

        assert result.exit_code == 0, result.output
        state = json.loads(state_file.read_text())
        first_hash = FileRuleSetStore(tmp_path / "rules" / "first_rules.pl").known_rulesets()[0]
        assert state["ruleset_hash"] == first_hash

    def test_init_resolves_top_system_alias(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        state_file = tmp_path / "state.json"
        config_path = _write_config(
            tmp_path,
            {
                "first_rules": "p(a).\n",
                "second_rules": "q(b).\n",
            },
            aliases={},
        )

        result = runner.invoke(
            main,
            [
                "init",
                "true",
                str(state_file),
                "--ruleset",
                "@top",
                "--config",
                str(config_path),
            ],
        )

        assert result.exit_code == 0, result.output
        state = json.loads(state_file.read_text())
        store = AggregateRuleSetStore(
            [
                FileRuleSetStore(tmp_path / "rules" / "first_rules.pl"),
                FileRuleSetStore(tmp_path / "rules" / "second_rules.pl"),
            ]
        )
        assert state["ruleset_hash"] == store.ruleset_hash

    def test_init_first_system_alias_requires_store(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        config_dir = tmp_path / ".constraint"
        config_dir.mkdir()
        config_path = config_dir / "config.yaml"
        config_path.write_text(yaml.safe_dump({"stores": [], "aliases": {}}))
        state_file = tmp_path / "state.json"

        result = runner.invoke(
            main,
            [
                "init",
                "true",
                str(state_file),
                "--ruleset",
                "@first",
                "--config",
                str(config_path),
            ],
        )

        assert result.exit_code != 0
        assert "@first" in result.output

    def test_init_store_name_starting_with_system_prefix_fails(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        config_dir = tmp_path / ".constraint"
        config_dir.mkdir()
        config_path = config_dir / "config.yaml"
        config_path.write_text(
            yaml.safe_dump(
                {
                    "stores": [
                        {
                            "type": "file",
                            "path": "rules/test.pl",
                            "name": "@named-rules",
                        }
                    ],
                    "aliases": {},
                }
            )
        )
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "test.pl").write_text(NONEMPTY_RULESET)
        state_file = tmp_path / "state.json"

        result = runner.invoke(
            main,
            [
                "init",
                "true",
                str(state_file),
                "--ruleset",
                "anything",
                "--config",
                str(config_path),
            ],
        )

        assert result.exit_code != 0
        assert "cannot start with '@'" in result.output


class TestResumeCommand:
    """Tests for the ``resume`` subcommand."""

    def test_resume_help(self, runner: CliRunner) -> None:
        """resume --help should display usage information."""
        result = runner.invoke(main, ["resume", "--help"])
        assert result.exit_code == 0
        assert "STATE_FILE" in result.output or "state" in result.output.lower()

    def test_resume_true_goal(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Resuming a 'true' goal should produce a solution."""
        # Set up state
        state_file = tmp_path / "state.json"
        config_path = _write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        runner.invoke(
            main,
            ["init", "true", str(state_file), "--ruleset", "test_rules", "--config", str(config_path)],
        )

        out_file = tmp_path / "out.json"
        result = runner.invoke(
            main, ["resume", str(state_file), str(out_file), "--config", str(config_path)]
        )
        assert result.exit_code == 0, result.output
        assert out_file.exists()
        state = json.loads(out_file.read_text())
        assert state["status"] == "solution"

    def test_resume_prints_status_summary(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """resume should print a one-line status summary to stdout."""
        state_file = tmp_path / "state.json"
        config_path = _write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        runner.invoke(
            main,
            ["init", "true", str(state_file), "--ruleset", "test_rules", "--config", str(config_path)],
        )
        out_file = tmp_path / "out.json"
        result = runner.invoke(
            main, ["resume", str(state_file), str(out_file), "--config", str(config_path)]
        )
        assert result.exit_code == 0
        assert "status:" in result.output

    def test_resume_yield_goal(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Resuming a goal with yield should produce suspended status."""
        state_file = tmp_path / "state.json"
        config_path = _write_config(
            tmp_path,
            {"test_rules": "rule(my_yield_goal, yield(checkpoint)).\n"},
            prolog_modes={"test_rules": "strict"},
        )
        runner.invoke(
            main,
            ["init", "my_yield_goal", str(state_file), "--ruleset", "test_rules", "--config", str(config_path)],
        )

        out_file = tmp_path / "out.json"
        result = runner.invoke(
            main, ["resume", str(state_file), str(out_file), "--config", str(config_path)]
        )
        assert result.exit_code == 0, result.output
        state = json.loads(out_file.read_text())
        assert state["status"] == "suspended"
        assert state["suspension"]["label"] == "checkpoint"
        assert "status: suspended" in result.output

    def test_resume_suspended_status_in_output(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """The stdout summary for suspended must include the label."""
        state_file = tmp_path / "state.json"
        config_path = _write_config(
            tmp_path,
            {"test_rules": "rule(my_yield_goal2, yield(my_label)).\n"},
            prolog_modes={"test_rules": "strict"},
        )
        runner.invoke(
            main,
            ["init", "my_yield_goal2", str(state_file), "--ruleset", "test_rules", "--config", str(config_path)],
        )
        out_file = tmp_path / "out.json"
        result = runner.invoke(
            main, ["resume", str(state_file), str(out_file), "--config", str(config_path)]
        )
        assert "my_label" in result.output

    def test_resume_overwrite_inplace(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """OUTPUT_FILE may be the same as STATE_FILE (overwrite in place)."""
        state_file = tmp_path / "state.json"
        config_path = _write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        runner.invoke(
            main,
            ["init", "true", str(state_file), "--ruleset", "test_rules", "--config", str(config_path)],
        )

        result = runner.invoke(
            main, ["resume", str(state_file), str(state_file), "--config", str(config_path)]
        )
        assert result.exit_code == 0, result.output
        state = json.loads(state_file.read_text())
        assert state["status"] == "solution"

    def test_resume_done_state_is_idempotent(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Resuming a 'done' state must write the same state unchanged."""
        state_file = tmp_path / "state.json"
        config_path = _write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        runner.invoke(
            main,
            [
                "init",
                "no_rule_cli_test_goal",
                str(state_file),
                "--ruleset",
                "test_rules",
                "--config",
                str(config_path),
            ],
        )
        out_file = tmp_path / "out.json"

        # First resume → done
        runner.invoke(
            main, ["resume", str(state_file), str(out_file), "--config", str(config_path)]
        )
        state_done = json.loads(out_file.read_text())
        assert state_done["status"] == "done"

        # Second resume → still done
        result2 = runner.invoke(
            main, ["resume", str(out_file), str(out_file), "--config", str(config_path)]
        )
        assert result2.exit_code == 0
        state_done2 = json.loads(out_file.read_text())
        assert state_done2["status"] == "done"

    def test_resume_nonexistent_state_fails(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Passing a nonexistent state file should exit with non-zero."""
        config_path = _write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        out_file = tmp_path / "out.json"
        result = runner.invoke(
            main,
            [
                "resume",
                str(tmp_path / "nonexistent.json"),
                str(out_file),
                "--config",
                str(config_path),
            ],
        )
        assert result.exit_code != 0

    def test_init_unknown_ruleset_fails(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """An unknown init ruleset alias/hash should fail clearly."""
        config_path = _write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        state_file = tmp_path / "state.json"
        result = runner.invoke(
            main,
            [
                "init",
                "true",
                str(state_file),
                "--ruleset",
                "missing_rules",
                "--config",
                str(config_path),
            ],
        )
        assert result.exit_code != 0
        assert "Unknown ruleset" in result.output

    def test_resume_missing_ruleset_hash_fails(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """resume should fail clearly when state lacks a pinned hash."""
        config_path = _write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        state_file = tmp_path / "state.json"
        state_file.write_text(
            json.dumps(
                {
                    "version": 0,
                    "original_goal": "true",
                    "branches": [{"goals": ["true"]}],
                    "status": "running",
                }
            )
        )
        out_file = tmp_path / "out.json"
        result = runner.invoke(
            main, ["resume", str(state_file), str(out_file), "--config", str(config_path)]
        )
        assert result.exit_code != 0
        assert "ruleset_hash" in result.output

    def test_init_empty_ruleset_fails(self, runner: CliRunner, tmp_path: Path) -> None:
        config_dir = tmp_path / ".constraint"
        rules_dir = tmp_path / "rules"
        config_dir.mkdir()
        rules_dir.mkdir()
        (rules_dir / "empty.pl").write_text("% empty\n")
        config_path = config_dir / "config.yaml"
        config_path.write_text(
            yaml.safe_dump(
                {
                    "stores": [{"type": "file", "path": "rules/empty.pl"}],
                    "aliases": {"empty_rules": "ignored"},
                }
            )
        )
        state_file = tmp_path / "state.json"

        result = runner.invoke(
            main,
            [
                "init",
                "true",
                str(state_file),
                "--ruleset",
                "empty_rules",
                "--config",
                str(config_path),
            ],
        )

        assert result.exit_code != 0
        assert "empty program" in result.output

    def test_resume_empty_ruleset_fails(self, runner: CliRunner, tmp_path: Path) -> None:
        config_dir = tmp_path / ".constraint"
        rules_dir = tmp_path / "rules"
        config_dir.mkdir()
        rules_dir.mkdir()
        (rules_dir / "empty.pl").write_text("% empty\n")
        config_path = config_dir / "config.yaml"
        config_path.write_text(
            yaml.safe_dump(
                {
                    "stores": [{"type": "file", "path": "rules/empty.pl"}],
                    "aliases": {},
                }
            )
        )
        state_file = tmp_path / "state.json"
        state_file.write_text(
            json.dumps(
                {
                    "version": 0,
                    "original_goal": "true",
                    "branches": [{"goals": ["true"]}],
                    "status": "running",
                    "ruleset_hash": "0" * 64,
                }
            )
        )
        out_file = tmp_path / "out.json"

        result = runner.invoke(
            main, ["resume", str(state_file), str(out_file), "--config", str(config_path)]
        )

        assert result.exit_code != 0
        assert "empty program" in result.output


class TestCLIRegistration:
    """Verify the new commands appear in the main help."""

    def test_init_registered(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "init" in result.output

    def test_resume_registered(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "resume" in result.output

    def test_store_registered(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "store" in result.output


class TestStoreCommand:
    """Tests for the ``store`` command group."""

    def test_store_list_includes_name_column_for_named_store(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        config_path = _write_config(
            tmp_path,
            {"test_rules": "p(a).\n"},
            aliases={},
            store_names={"test_rules": "named-rules"},
        )

        result = runner.invoke(main, ["store", "list", "--config", str(config_path)])

        assert result.exit_code == 0, result.output
        lines = result.output.strip().splitlines()
        assert lines[0].split() == ["type", "name", "path", "hash"]
        assert "@top" in lines[1]
        assert "named-rules" in lines[2]
        assert str(tmp_path / "rules" / "test_rules.pl") in lines[2]

    def test_store_list_omits_name_column_for_anonymous_stores(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        config_path = _write_config(tmp_path, {"test_rules": "p(a).\n"}, aliases={})

        result = runner.invoke(main, ["store", "list", "--config", str(config_path)])

        assert result.exit_code == 0, result.output
        assert result.output.strip().splitlines()[0].split() == ["type", "name", "path", "hash"]

    def test_store_list_raw_output_starts_with_top_row(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        config_path = _write_config(
            tmp_path,
            {
                "first_rules": "p(a).\n",
                "second_rules": "q(b).\n",
            },
            aliases={},
        )

        result = runner.invoke(main, ["store", "list", "--config", str(config_path)])

        assert result.exit_code == 0, result.output
        lines = result.output.strip().splitlines()
        assert lines[1].split()[0:2] == ["system", "@top"]
        assert lines[2].split()[0] == "file"

    def test_store_list_json_output(self, runner: CliRunner, tmp_path: Path) -> None:
        config_path = _write_config(
            tmp_path,
            {"test_rules": "p(a).\n"},
            aliases={},
            store_names={"test_rules": "named-rules"},
        )

        result = runner.invoke(
            main,
            ["store", "list", "--config", str(config_path), "--format", "json"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        aggregate = AggregateRuleSetStore(
            [FileRuleSetStore(tmp_path / "rules" / "test_rules.pl", name="named-rules")]
        )
        assert payload == [
            {
                "type": "system",
                "name": "@top",
                "hash": aggregate.ruleset_hash,
            },
            {
                "type": "file",
                "name": "named-rules",
                "path": str(tmp_path / "rules" / "test_rules.pl"),
                "hash": FileRuleSetStore(tmp_path / "rules" / "test_rules.pl").known_rulesets()[0],
            }
        ]

    def test_store_list_json_output_starts_with_top_entry(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        config_path = _write_config(
            tmp_path,
            {
                "first_rules": "p(a).\n",
                "second_rules": "q(b).\n",
            },
            aliases={},
        )

        result = runner.invoke(
            main,
            ["store", "list", "--config", str(config_path), "--format", "json"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload[0]["type"] == "system"
        assert payload[0]["name"] == "@top"
        assert "path" not in payload[0]

    def test_store_list_json_pretty_print(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        config_path = _write_config(tmp_path, {"test_rules": "p(a).\n"}, aliases={})

        result = runner.invoke(
            main,
            [
                "store",
                "list",
                "--config",
                str(config_path),
                "--format",
                "json",
                "--pretty-print",
            ],
        )

        assert result.exit_code == 0, result.output
        assert result.output.startswith("[\n  {")
