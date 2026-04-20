from __future__ import annotations

import math
import re

import simpleeval


def remove_comments(script: str) -> str:
    """Remove inline comments while preserving meaningful lines."""
    return "\n".join(
        line.split("#", 1)[0].rstrip()
        for line in script.splitlines()
        if line.split("#", 1)[0].strip()
    )


def remove_prints(script: str) -> str:
    """Remove lines that start with ``print``."""
    return "\n".join(line for line in script.splitlines() if not line.lstrip().startswith("print"))


def merge_ampersand_lines(script: str) -> str:
    """Merge lines ending in ``&`` into one logical line."""
    merged_lines: list[str] = []
    buffer: str | None = None

    for line in script.splitlines():
        stripped = line.rstrip()
        if stripped.endswith("&"):
            buffer = (buffer or "") + " " + stripped[:-1].strip()
        else:
            merged_lines.append((buffer + " " + stripped).strip() if buffer else stripped)
            buffer = None

    if buffer:
        merged_lines.append(buffer.strip())

    return "\n".join(merged_lines)


def parse_variable_line(line: str) -> tuple[str | None, str | None, str | None]:
    """Parse supported LAMMPS ``variable`` statements."""
    tokens = line.split(maxsplit=3)
    if len(tokens) < 3 or tokens[0] != "variable":
        return None, None, None

    var_name = tokens[1]
    var_type = tokens[2]
    if var_type in {"equal", "index", "string"}:
        return var_name, var_type, tokens[3] if len(tokens) == 4 else None

    return None, None, None


def process_and_evaluate_variables(script: str) -> str:
    """Resolve simple variable references in a script."""
    script_lines = script.splitlines()
    var_dict: dict[str, str] = {}
    variable_definitions: dict[str, tuple[str, str]] = {}
    processed_lines: list[str] = []

    for line in script_lines:
        if line.startswith("variable"):
            var_name, var_type, expr = parse_variable_line(line)
            if var_name and var_type and expr:
                if var_type in {"string", "index"}:
                    var_dict[var_name] = expr
                else:
                    variable_definitions[var_name] = (var_type, expr)
            else:
                # Preserve unsupported variable forms rather than dropping them.
                processed_lines.append(line)
        else:
            processed_lines.append(line)

    dependency_graph: dict[str, set[str]] = {}
    for var_name, (_, expr) in variable_definitions.items():
        dependencies = set(re.findall(r"v_([a-zA-Z_]\w*)|\${([a-zA-Z_]\w*)}", expr))
        dependency_graph[var_name] = {
            dep[0] or dep[1]
            for dep in dependencies
            if (dep[0] or dep[1]) in variable_definitions
        }

    resolved_vars: set[str] = set()
    while variable_definitions:
        progress_made = False
        for var_name, (_, expr) in list(variable_definitions.items()):
            if dependency_graph[var_name].issubset(resolved_vars):
                expr = re.sub(
                    r"v_([a-zA-Z_]\w*)|\${([a-zA-Z_]\w*)}",
                    lambda match: str(
                        var_dict.get(
                            match.group(1) or match.group(2),
                            f"v_{match.group(1) or match.group(2)}",
                        )
                    ),
                    expr,
                )
                expr = expr.replace("^", "**")
                try:
                    result = simpleeval.simple_eval(
                        expr,
                        names={"pi": math.pi},
                        functions={
                            "sqrt": math.sqrt,
                            "round": round,
                            "ceil": math.ceil,
                            "floor": math.floor,
                            "exp": math.exp,
                        },
                    )
                except Exception:
                    continue

                if isinstance(result, float) and result.is_integer():
                    result = int(result)
                var_dict[var_name] = str(result)
                resolved_vars.add(var_name)
                del variable_definitions[var_name]
                progress_made = True

        if not progress_made:
            break

    new_lines: list[str] = []
    for line in processed_lines:
        line = re.sub(
            r"v_([a-zA-Z_]\w*)|\${([a-zA-Z_]\w*)}",
            lambda match: str(
                var_dict.get(
                    match.group(1) or match.group(2),
                    f"v_{match.group(1) or match.group(2)}",
                )
            ),
            line,
        )
        new_lines.append(line)

    return "\n".join(new_lines)


def evaluate_expressions(script: str) -> str:
    """Evaluate pure arithmetic tokens that contain no variable references."""
    arithmetic_pattern = re.compile(r"^[\d+\-*/().eE]+$")

    def evaluate_token(token: str) -> str:
        if arithmetic_pattern.fullmatch(token):
            try:
                value = simpleeval.simple_eval(
                    token.replace("^", "**"),
                    names={"pi": math.pi},
                    functions={"sqrt": math.sqrt, "round": round},
                )
            except Exception:
                return token

            if isinstance(value, float) and value.is_integer():
                value = int(value)
            return str(value)

        return token

    return "\n".join(
        " ".join(evaluate_token(token) for token in line.split())
        for line in script.splitlines()
    )


def evaluate_lammps_arithmetic(script: str) -> str:
    """Evaluate purely numeric ``$(...)`` expressions."""
    expr_pat = re.compile(r"\$\(\s*([0-9+\-*/^(). eE]+?)\s*\)")

    def repl(match: re.Match[str]) -> str:
        expr = match.group(1).replace("^", "**")
        try:
            value = simpleeval.simple_eval(
                expr,
                names={"pi": math.pi},
                functions={"sqrt": math.sqrt, "round": round},
            )
        except Exception:
            return match.group(0)

        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return str(value)

    return expr_pat.sub(repl, script)


def expand_loops(script: str) -> str:
    """Expand simple ``variable ... loop`` constructs when possible."""
    lines = script.splitlines()
    expanded_lines: list[str] = []
    loop_label = None
    loop_var_name = None
    loop_count = None

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("label "):
            loop_label = stripped.split()[1]
        elif stripped.startswith("variable ") and " loop " in stripped:
            parts = stripped.split()
            if len(parts) >= 4 and parts[2] == "loop" and parts[3].isdigit():
                loop_var_name = parts[1]
                loop_count = int(parts[3])

    if not loop_var_name or not loop_count:
        return script

    for iteration in range(1, loop_count + 1):
        for line in lines:
            stripped = line.strip()
            if (
                stripped.startswith(f"variable {loop_var_name} loop")
                or stripped.startswith(f"next {loop_var_name}")
                or stripped.startswith(f"jump SELF {loop_label}")
            ):
                continue

            if stripped.startswith("if "):
                match = re.match(r'^if\s+"([^"]+)"\s+then\s+(.*)$', stripped)
                if match:
                    condition, then_part = match.groups()
                    condition_eval = condition.replace(f"${{{loop_var_name}}}", str(iteration))
                    if re.fullmatch(r"[\d\s<>=!]+", condition_eval):
                        try:
                            if simpleeval.simple_eval(condition_eval):
                                expanded_lines.extend(re.findall(r'"([^"]*)"', then_part))
                        except Exception:
                            pass
                    continue

            expanded_lines.append(line)

    return "\n".join(expanded_lines)


def sanitize_script(script: str) -> str:
    """Run the ez-pipeline sanitizer compatibility layer."""
    script = remove_comments(script)
    script = remove_prints(script)
    script = merge_ampersand_lines(script)
    script = expand_loops(script)
    script = process_and_evaluate_variables(script)
    script = evaluate_expressions(script)
    script = evaluate_lammps_arithmetic(script)
    return script.rstrip() + "\n"
