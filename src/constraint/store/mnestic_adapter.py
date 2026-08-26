"""Mnestic (CozoDB) adapter for the constraint ruleset store.

This module provides the schema descriptor dataclasses and MnesticAdapter
that MnesticRuleSetStore builds against. The adapter opens a read-only
rocksdb-backed mnestic database, discovers its schema generically from
CozoDB's ``::relations`` and ``::columns`` system ops, and executes
read-only CozoScript.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mnestic import CozoDbPy

from constraint.parser import Atom, Compound, Integer, List, Variable, parse_term

# ---------------------------------------------------------------------------
# Module-level store-name → MnesticAdapter registry
# ---------------------------------------------------------------------------

_registry: dict[str, MnesticAdapter] = {}


def register(name: str, adapter: MnesticAdapter) -> None:
    """Bind *name* to *adapter* in the module-level registry.

    Args:
        name: The store name to register under.
        adapter: The MnesticAdapter instance to associate with *name*.
    """
    _registry[name] = adapter


def lookup(name: str) -> MnesticAdapter:
    """Return the MnesticAdapter registered under *name*.

    Args:
        name: The store name to look up.

    Returns:
        The registered MnesticAdapter instance.

    Raises:
        KeyError: If *name* has not been registered.
    """
    try:
        return _registry[name]
    except KeyError:
        raise KeyError(f"Unknown mnestic store: '{name}'") from None


# ---------------------------------------------------------------------------
# Schema descriptors
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ColumnDescriptor:
    """Descriptor for a single column in a discovered relation."""

    name: str
    type: str
    is_key: bool


@dataclass(frozen=True)
class RelationDescriptor:
    """Descriptor for a discovered relation (table).

    ``columns`` is an ordered list: key column(s) first, then value columns
    in declaration order. ``arity`` always equals ``len(columns)``.
    """

    name: str
    columns: list[ColumnDescriptor]
    arity: int = field(default=0)

    def __post_init__(self) -> None:
        # A frozen dataclass requires object.__setattr__ for computed fields.
        # Always derive arity from the actual column list so the invariant
        # ``arity == len(columns)`` holds regardless of what was passed in.
        object.__setattr__(self, "arity", len(self.columns))


# ---------------------------------------------------------------------------
# Compiled-query internal structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DerivedRule:
    """A derived rule extracted from the compiled query's ``derived([...])`` field.

    ``head`` is the compound term defining the derived relation (e.g.
    ``descendant(anc, desc)``).  ``body`` is the list of body literals
    (AST nodes) that define the rule.
    """

    head: Compound
    body: list[Any]


@dataclass(frozen=True)
class BaseLiteral:
    """A validated base literal referencing a schema relation.

    ``relation`` is the relation name.  ``column_bindings`` maps each
    column name to its value token (an atom name or integer string).
    """

    relation: str
    column_bindings: dict[str, str]


@dataclass(frozen=True)
class DerivedLiteral:
    """A derived literal in the query goals.

    ``head_functor`` is the functor of the derived relation.
    ``args`` are the atom arguments (column tokens).
    """

    head_functor: str
    args: list[Atom]


@dataclass(frozen=True)
class Guard:
    """A guard (builtin constraint) in the query goals.

    ``functor`` is the guard functor (currently only ``!=``).
    ``args`` are the atom arguments.
    """

    functor: str
    args: list[Atom]


@dataclass(frozen=True)
class ClassifiedGoal:
    """A classified goal literal from the compiled query.

    ``kind`` is one of ``"base"``, ``"derived"``, or ``"guard"``.
    ``detail`` holds the corresponding typed structure.
    """

    kind: str
    detail: BaseLiteral | DerivedLiteral | Guard


@dataclass(frozen=True)
class ParsedCompiledQuery:
    """The validated, classified internal structure from a compiled query.

    This is the input that the next task's CozoScript assembler consumes.
    """

    store_name: str
    projection_columns: list[str]
    derived_rules: list[DerivedRule]
    goals: list[ClassifiedGoal]


class MnesticAdapter:
    """Adapter to a mnestic (CozoDB) database.

    Opens the rocksdb-backed database at *path* and provides read-only
    script execution and generic schema discovery.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self._db = CozoDbPy("rocksdb", path, "")

    def run_script(
        self,
        script: str,
        params: dict[str, Any] | None = None,
        immutable: bool = True,
    ) -> dict[str, Any]:
        """Execute a CozoScript against the database.

        Args:
            script: The CozoScript to execute.
            params: Optional parameters for the script.
            immutable: Whether the script is read-only (default True).

        Returns:
            The raw CozoDB result dict with ``headers``, ``rows``, and
            ``next`` keys.
        """
        if params is None:
            params = {}
        return self._db.run_script(script, params, immutable)

    def discover_schema(self) -> list[RelationDescriptor]:
        """Discover the schema of the database.

        Runs ``::relations`` to list stored relations, then
        ``::columns <relation>`` for each to obtain column metadata.
        Columns are ordered key-first-then-value by their positional index
        so that base-predicate generation is deterministic.

        Returns:
            A list of RelationDescriptor objects, one per stored relation.
        """
        relations_result = self.run_script("::relations")
        relations_headers = relations_result["headers"]
        relations_rows = relations_result["rows"]

        descriptors: list[RelationDescriptor] = []
        for row in relations_rows:
            rel = dict(zip(relations_headers, row, strict=False))
            rel_name: str = rel["name"]

            columns_result = self.run_script(f"::columns {rel_name}")
            col_headers = columns_result["headers"]
            col_rows = columns_result["rows"]

            # Build column descriptors, sorting by (not is_key, index)
            # so key columns come first, then value columns in declaration order.
            raw_columns: list[dict[str, Any]] = [
                dict(zip(col_headers, cr, strict=False)) for cr in col_rows
            ]
            raw_columns.sort(key=lambda c: (not c["is_key"], c["index"]))

            columns = [
                ColumnDescriptor(
                    name=col["column"],
                    type=col["type"],
                    is_key=bool(col["is_key"]),
                )
                for col in raw_columns
            ]

            descriptors.append(RelationDescriptor(name=rel_name, columns=columns))

        return descriptors

    # ------------------------------------------------------------------
    # Compiled-query parsing, validation, and classification
    # ------------------------------------------------------------------

    def parse_compiled_query(
        self,
        compiled_atom: str,
        obligations_atom: str,
    ) -> ParsedCompiledQuery:
        """Parse, validate, and classify a serialized compiled query.

        Args:
            compiled_atom: The serialized ``compiled_query(...)`` term.
            obligations_atom: The serialized obligations term (parsed for
                forward compatibility, not yet used in v1).

        Returns:
            A ``ParsedCompiledQuery`` with validated internal structure.

        Raises:
            ValueError: If the term fails any validation step.
        """
        # Parse both atoms
        compiled = parse_term(compiled_atom)
        # Parse obligations for forward compatibility (unused in v1)
        parse_term(obligations_atom)

        # Validate top-level structure
        if not isinstance(compiled, Compound) or compiled.functor != "compiled_query":
            raise ValueError(
                f"Expected compiled_query/4 term, got "
                f"{compiled.functor if isinstance(compiled, Compound) else type(compiled).__name__}"
            )

        if len(compiled.args) != 4:
            raise ValueError(
                f"Expected compiled_query/4 with 4 arguments, got {len(compiled.args)}"
            )

        store_term, template_term, derived_term, goals_term = compiled.args

        # --- Extract store name ---
        store_name = self._extract_store_name(store_term)

        # --- Extract projection columns from template ---
        projection_columns = self._extract_projection_columns(template_term)

        # --- Extract derived rules ---
        derived_rules = self._extract_derived_rules(derived_term)

        # --- Extract goals ---
        goals_literals = self._extract_goals_list(goals_term)

        # --- Ground-invariant check ---
        self._check_ground(compiled)

        # --- Classify goals against schema and derived heads ---
        schema = self.discover_schema()
        classified_goals = self._classify_goals(
            goals_literals, derived_rules, schema
        )

        return ParsedCompiledQuery(
            store_name=store_name,
            projection_columns=projection_columns,
            derived_rules=derived_rules,
            goals=classified_goals,
        )

    # ------------------------------------------------------------------
    # Internal helpers — extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_store_name(store_term: Any) -> str:
        """Extract the store name from ``store(Name)``."""
        if not isinstance(store_term, Compound) or store_term.functor != "store":
            raise ValueError(
                f"Expected store(Name), got "
                f"{store_term.functor if isinstance(store_term, Compound) else type(store_term).__name__}"
            )
        if len(store_term.args) != 1:
            raise ValueError(
                f"store/1 expects exactly 1 argument, got {len(store_term.args)}"
            )
        name_arg = store_term.args[0]
        if not isinstance(name_arg, Atom):
            raise ValueError(
                f"Store name must be an atom, got {type(name_arg).__name__}: {name_arg}"
            )
        return name_arg.value

    @staticmethod
    def _extract_projection_columns(template_term: Any) -> list[str]:
        """Extract projection column names from ``template(ResultName, Columns)``."""
        if not isinstance(template_term, Compound) or template_term.functor != "template":
            raise ValueError(
                f"Expected template(ResultName, Columns), got "
                f"{template_term.functor if isinstance(template_term, Compound) else type(template_term).__name__}"
            )
        if len(template_term.args) != 2:
            raise ValueError(
                f"template/2 expects exactly 2 arguments, got {len(template_term.args)}"
            )
        cols_node = template_term.args[1]
        if not isinstance(cols_node, List):
            raise ValueError(
                f"Template columns must be a list, got {type(cols_node).__name__}"
            )
        columns: list[str] = []
        for col in cols_node.elements:
            if not isinstance(col, Atom):
                raise ValueError(
                    f"Projection column must be an atom, got {type(col).__name__}: {col}"
                )
            columns.append(col.value)
        return columns

    @staticmethod
    def _extract_derived_rules(derived_term: Any) -> list[DerivedRule]:
        """Extract derived rules from ``derived([rule(Head, Body), ...])``."""
        if not isinstance(derived_term, Compound) or derived_term.functor != "derived":
            raise ValueError(
                f"Expected derived([...]), got "
                f"{derived_term.functor if isinstance(derived_term, Compound) else type(derived_term).__name__}"
            )
        if len(derived_term.args) != 1:
            raise ValueError(
                f"derived/1 expects exactly 1 argument, got {len(derived_term.args)}"
            )
        list_node = derived_term.args[0]
        if not isinstance(list_node, List):
            raise ValueError(
                f"Derived argument must be a list, got {type(list_node).__name__}"
            )
        rules: list[DerivedRule] = []
        for item in list_node.elements:
            if not isinstance(item, Compound) or item.functor != "rule" or len(item.args) != 2:
                raise ValueError(
                    f"Expected rule(Head, Body) in derived list, got {item}"
                )
            head, body = item.args
            if not isinstance(head, Compound):
                raise ValueError(
                    f"Derived rule head must be a compound term, got "
                    f"{type(head).__name__}: {head}"
                )
            # Body is a list of literals (or a single compound)
            body_literals: list[Any] = []
            if isinstance(body, List):
                body_literals = list(body.elements)
            elif isinstance(body, Compound):
                body_literals = [body]
            else:
                raise ValueError(
                    f"Derived rule body must be a list or compound term, got "
                    f"{type(body).__name__}: {body}"
                )
            rules.append(DerivedRule(head=head, body=body_literals))
        return rules

    @staticmethod
    def _extract_goals_list(goals_term: Any) -> list[Any]:
        """Extract the list of goal literals from ``goals([...])``."""
        if not isinstance(goals_term, Compound) or goals_term.functor != "goals":
            raise ValueError(
                f"Expected goals([...]), got "
                f"{goals_term.functor if isinstance(goals_term, Compound) else type(goals_term).__name__}"
            )
        if len(goals_term.args) != 1:
            raise ValueError(
                f"goals/1 expects exactly 1 argument, got {len(goals_term.args)}"
            )
        list_node = goals_term.args[0]
        if not isinstance(list_node, List):
            raise ValueError(
                f"Goals argument must be a list, got {type(list_node).__name__}"
            )
        return list(list_node.elements)

    # ------------------------------------------------------------------
    # Ground-invariant check
    # ------------------------------------------------------------------

    @staticmethod
    def _find_variables(node: Any) -> list[Variable]:
        """Recursively find all ``Variable`` nodes in an AST subtree."""
        variables: list[Variable] = []
        if isinstance(node, Variable):
            variables.append(node)
        elif isinstance(node, Compound):
            for arg in node.args:
                variables.extend(MnesticAdapter._find_variables(arg))
        elif isinstance(node, List):
            for elem in node.elements:
                variables.extend(MnesticAdapter._find_variables(elem))
            if node.tail is not None:
                variables.extend(MnesticAdapter._find_variables(node.tail))
        return variables

    def _check_ground(self, term: Any) -> None:
        """Check that *term* contains no ``Variable`` nodes.

        A well-formed compiled term must be fully ground (only atoms and
        integers as values) in all non-projection positions.

        Raises:
            ValueError: If a ``Variable`` node is found anywhere in the term.
        """
        variables = self._find_variables(term)
        if variables:
            var_names = sorted({v.name for v in variables})
            raise ValueError(
                f"Compiled query term contains unbound variables in "
                f"non-projection positions: {', '.join(var_names)}. "
                f"All base-literal values, derived-rule body literals, "
                f"and guard arguments must be ground (atoms or integers)."
            )

    # ------------------------------------------------------------------
    # Goal classification
    # ------------------------------------------------------------------

    def _classify_goals(
        self,
        literals: list[Any],
        derived_rules: list[DerivedRule],
        schema: list[RelationDescriptor],
    ) -> list[ClassifiedGoal]:
        """Classify each goal literal as base, derived, or guard.

        Args:
            literals: The goal literals from the compiled query.
            derived_rules: The derived rules from the compiled query.
            schema: The discovered schema relations.

        Returns:
            A list of ``ClassifiedGoal`` objects.

        Raises:
            ValueError: If a literal cannot be classified or fails validation.
        """
        derived_functors = {rule.head.functor for rule in derived_rules}
        schema_functors = {rel.name for rel in schema}

        classified: list[ClassifiedGoal] = []
        for literal in literals:
            if not isinstance(literal, Compound):
                raise ValueError(
                    f"Expected compound term for goal literal, got "
                    f"{type(literal).__name__}: {literal}"
                )

            functor = literal.functor

            # --- Guard: != ---
            if functor == "!=":
                if len(literal.args) != 2:
                    raise ValueError(
                        f"!= guard must have exactly 2 arguments, got {len(literal.args)}"
                    )
                for arg in literal.args:
                    if not isinstance(arg, (Atom, Integer)):
                        raise ValueError(
                            f"!= guard arguments must be atoms or integers, got "
                            f"{type(arg).__name__}: {arg}"
                        )
                classified.append(
                    ClassifiedGoal(
                        kind="guard",
                        detail=Guard(functor="!=", args=list(literal.args)),
                    )
                )
                continue

            # --- Derived literal ---
            if functor in derived_functors:
                for arg in literal.args:
                    if not isinstance(arg, (Atom, Integer)):
                        raise ValueError(
                            f"Derived literal arguments must be atoms or integers, got "
                            f"{type(arg).__name__}: {arg}"
                        )
                classified.append(
                    ClassifiedGoal(
                        kind="derived",
                        detail=DerivedLiteral(
                            head_functor=functor, args=list(literal.args)
                        ),
                    )
                )
                continue

            # --- Base literal (must validate against schema) ---
            if functor in schema_functors:
                base = self._validate_base_literal(literal, schema)
                classified.append(ClassifiedGoal(kind="base", detail=base))
                continue

            # --- Unknown literal ---
            raise ValueError(
                f"Unknown goal literal '{functor}': not a recognized guard (!=), "
                f"not a derived rule head (known: {sorted(derived_functors) or 'none'}), "
                f"and not a known schema relation (known: {sorted(schema_functors) or 'none'})."
            )

        return classified

    # ------------------------------------------------------------------
    # Base literal validation
    # ------------------------------------------------------------------

    def _validate_base_literal(
        self,
        literal: Compound,
        schema: list[RelationDescriptor],
    ) -> BaseLiteral:
        """Validate a base literal against the discovered schema.

        Args:
            literal: The base literal compound term.
            schema: The discovered schema relations.

        Returns:
            A ``BaseLiteral`` with verified relation and column bindings.

        Raises:
            ValueError: If the relation or any column is invalid.
        """
        functor = literal.functor

        # Find the relation in the schema
        rel_descriptor: RelationDescriptor | None = None
        for rel in schema:
            if rel.name == functor:
                rel_descriptor = rel
                break

        if rel_descriptor is None:
            raise ValueError(
                f"Unknown relation '{functor}': no matching relation found in "
                f"the discovered schema. "
                f"Known relations: {sorted(r.name for r in schema)}"
            )

        # The literal should have a single arg which is a list of Key-Value pairs
        if len(literal.args) != 1:
            raise ValueError(
                f"Base literal '{functor}' must have a single argument "
                f"(a list of Key-Value pairs), got {len(literal.args)} arguments"
            )

        kv_list = literal.args[0]
        if not isinstance(kv_list, List):
            raise ValueError(
                f"Base literal '{functor}' argument must be a list of "
                f"Key-Value pairs, got {type(kv_list).__name__}"
            )

        # Extract column bindings
        column_bindings: dict[str, str] = {}
        known_columns = {col.name for col in rel_descriptor.columns}

        for kv in kv_list.elements:
            if not isinstance(kv, Compound) or kv.functor != "-" or len(kv.args) != 2:
                raise ValueError(
                    f"Expected Key-Value pair (Key-Value) in base literal "
                    f"'{functor}', got {kv}"
                )

            key = kv.args[0]
            value = kv.args[1]

            if not isinstance(key, Atom):
                raise ValueError(
                    f"Key in Key-Value pair must be an atom, got "
                    f"{type(key).__name__}: {key}"
                )

            if not isinstance(value, (Atom, Integer)):
                raise ValueError(
                    f"Value in Key-Value pair must be an atom or integer, got "
                    f"{type(value).__name__}: {value}"
                )

            col_name = key.value

            if col_name not in known_columns:
                raise ValueError(
                    f"Unknown column '{col_name}' in base literal '{functor}'. "
                    f"Known columns: {sorted(known_columns)}"
                )

            if col_name in column_bindings:
                raise ValueError(
                    f"Duplicate column '{col_name}' in base literal '{functor}'"
                )

            if isinstance(value, Atom):
                column_bindings[col_name] = value.value
            else:
                column_bindings[col_name] = str(value.value)

        return BaseLiteral(relation=functor, column_bindings=column_bindings)

    # ------------------------------------------------------------------
    # CozoScript assembly
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_column_tokens(
        parsed: ParsedCompiledQuery,
    ) -> set[str]:
        """Collect all column-token atom names from the parsed query.

        These are atoms that represent variable-like bindings (as opposed
        to string constants) and should be rendered unquoted in CozoScript.
        """
        tokens: set[str] = set(parsed.projection_columns)

        # Add arguments from derived rule heads
        for rule in parsed.derived_rules:
            for arg in rule.head.args:
                if isinstance(arg, Atom):
                    tokens.add(arg.value)

        # Add arguments from classified goals (derived and guard)
        for goal in parsed.goals:
            if goal.kind == "derived" or goal.kind == "guard":
                for arg in goal.detail.args:
                    if isinstance(arg, Atom):
                        tokens.add(arg.value)

        # Add arguments from derived rule body literals
        for rule in parsed.derived_rules:
            for literal in rule.body:
                if isinstance(literal, Compound):
                    # Derived literal or guard in body
                    if literal.functor == "!=" or any(
                        literal.functor == r.head.functor for r in parsed.derived_rules
                    ):
                        for arg in literal.args:
                            if isinstance(arg, Atom):
                                tokens.add(arg.value)
                    # Base literal: extract values from key-value pairs
                    elif len(literal.args) == 1 and isinstance(literal.args[0], List):
                        for kv in literal.args[0].elements:
                            if isinstance(kv, Compound) and kv.functor == "-" and len(kv.args) == 2:
                                val = kv.args[1]
                                if isinstance(val, Atom):
                                    tokens.add(val.value)

        return tokens

    @staticmethod
    def _render_value(value: str, column_tokens: set[str]) -> str:
        """Render a base-literal value for CozoScript.

        Column tokens (variable-like bindings) are rendered unquoted.
        Integer strings are rendered as-is.
        String constants are single-quoted.
        """
        if value in column_tokens:
            return value
        # Check if it is an integer
        try:
            int(value)
            return value
        except ValueError:
            pass
        # String constant: single-quote with escaping
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"

    @staticmethod
    def _render_base_literal(
        relation: str,
        column_bindings: dict[str, str],
        column_tokens: set[str],
    ) -> str:
        """Render a base literal as ``*rel{col: val, ...}``."""
        pairs = ", ".join(
            f"{col}: {MnesticAdapter._render_value(val, column_tokens)}"
            for col, val in column_bindings.items()
        )
        return f"*{relation}{{{pairs}}}"

    @staticmethod
    def _render_derived_head(head: Compound) -> str:
        """Render a derived rule head as ``name[arg1, arg2, ...]``."""
        args_str = ", ".join(str(arg) for arg in head.args)
        return f"{head.functor}[{args_str}]"

    @staticmethod
    def _render_raw_literal(
        literal: Any,
        column_tokens: set[str],
        derived_functors: set[str],
    ) -> str:
        """Render a raw AST literal (from a derived rule body) as CozoScript."""
        if not isinstance(literal, Compound):
            return str(literal)

        functor = literal.functor

        # Guard: !=
        if functor == "!=":
            if len(literal.args) == 2:
                return f"{literal.args[0]} != {literal.args[1]}"
            return str(literal)

        # Derived literal (use square brackets in CozoScript)
        if functor in derived_functors:
            args_str = ", ".join(str(arg) for arg in literal.args)
            return f"{functor}[{args_str}]"

        # Base literal: *rel{col: val, ...}
        if len(literal.args) == 1 and isinstance(literal.args[0], List):
            pairs: list[str] = []
            for kv in literal.args[0].elements:
                if isinstance(kv, Compound) and kv.functor == "-" and len(kv.args) == 2:
                    key = str(kv.args[0])
                    val_node = kv.args[1]
                    if isinstance(val_node, Atom):
                        val = MnesticAdapter._render_value(
                            val_node.value, column_tokens
                        )
                    elif isinstance(val_node, Integer):
                        val = str(val_node.value)
                    else:
                        val = str(val_node)
                    pairs.append(f"{key}: {val}")
            return f"*{functor}{{{', '.join(pairs)}}}"

        # Fallback
        return str(literal)

    @staticmethod
    def _render_classified_goal(
        goal: ClassifiedGoal,
        column_tokens: set[str],
    ) -> str:
        """Render a classified goal as a CozoScript body literal."""
        if goal.kind == "base":
            base = goal.detail
            assert isinstance(base, BaseLiteral)
            return MnesticAdapter._render_base_literal(
                base.relation, base.column_bindings, column_tokens
            )
        elif goal.kind == "derived":
            derived = goal.detail
            assert isinstance(derived, DerivedLiteral)
            args_str = ", ".join(str(arg) for arg in derived.args)
            return f"{derived.head_functor}[{args_str}]"
        elif goal.kind == "guard":
            guard = goal.detail
            assert isinstance(guard, Guard)
            if len(guard.args) == 2:
                return f"{guard.args[0]} != {guard.args[1]}"
            return str(guard)
        else:
            raise ValueError(f"Unknown goal kind: {goal.kind}")

    def _assemble_script(self, parsed: ParsedCompiledQuery) -> str:
        """Assemble a CozoScript string from a parsed compiled query.

        Emits derived rules first (all clauses per relation, in declaration
        order), then the query head ``?[proj...] := body``.

        Args:
            parsed: The validated, classified compiled query.

        Returns:
            A CozoScript string ready for execution.
        """
        column_tokens = self._collect_column_tokens(parsed)
        derived_functors = {rule.head.functor for rule in parsed.derived_rules}

        parts: list[str] = []

        # --- Derived rules ---
        for rule in parsed.derived_rules:
            head_str = self._render_derived_head(rule.head)
            body_strs = [
                self._render_raw_literal(lit, column_tokens, derived_functors)
                for lit in rule.body
            ]
            parts.append(f"{head_str} := {', '.join(body_strs)}")

        # --- Query head ---
        proj_str = ", ".join(parsed.projection_columns)
        body_strs = [
            self._render_classified_goal(goal, column_tokens)
            for goal in parsed.goals
        ]
        parts.append(f"?[{proj_str}] := {', '.join(body_strs)}")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Orchestrator: parse → assemble → execute
    # ------------------------------------------------------------------

    def compile_and_run(
        self,
        compiled_atom: str,
        obligations_atom: str,
    ) -> list[list[str | int]]:
        """Parse a compiled query, assemble CozoScript, execute it, and
        return the raw result rows.

        Args:
            compiled_atom: The serialized ``compiled_query(...)`` term.
            obligations_atom: The serialized obligations term.

        Returns:
            The ``rows`` list-of-lists from the CozoDB result, in
            projection column order.
        """
        parsed = self.parse_compiled_query(compiled_atom, obligations_atom)
        script = self._assemble_script(parsed)
        result = self.run_script(script, {}, immutable=True)
        return result["rows"]
