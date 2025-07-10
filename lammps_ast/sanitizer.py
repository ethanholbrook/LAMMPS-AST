
import re
import math
import simpleeval

def remove_comments(script):
    """Removes inline comments while preserving meaningful lines."""
    return '\n'.join(line.split('#', 1)[0].rstrip() for line in script.splitlines() if line.split('#', 1)[0].strip())

def remove_prints(script):
    """Removes lines that start with 'print'."""
    return '\n'.join(line for line in script.splitlines() if not line.lstrip().startswith('print'))


def merge_ampersand_lines(script):
    """Merges lines ending with '&' into a single line while preserving spacing."""
    merged_lines, buffer = [], None

    for line in script.splitlines():
        stripped = line.rstrip()
        if stripped.endswith('&'):
            buffer = (buffer or "") + " " + stripped[:-1].strip()
        else:
            merged_lines.append((buffer + " " + stripped).strip() if buffer else stripped)
            buffer = None  # Reset buffer after appending

    if buffer:
        merged_lines.append(buffer.strip())

    return '\n'.join(merged_lines)

def parse_variable_line(line):
    """Extracts variable name and expression from a LAMMPS variable definition line."""
    tokens = line.split(maxsplit=3)  # Adjusted to ensure proper parsing

    if len(tokens) < 3 or tokens[0] != "variable":
        return None, None

    var_name = tokens[1]
    var_type = tokens[2]

    # Handle "index" type variables correctly
    if var_type == "index":
        return var_name, tokens[3] if len(tokens) == 4 else None

    # Handle "equal" type variables
    if var_type == "equal":
        return var_name, tokens[3] if len(tokens) == 4 else None

    return None, None

def process_and_evaluate_variables(script):
    """Replaces variables (`${var}` and `v_var`) while ensuring dependencies are handled iteratively."""
    script_lines = script.splitlines()
    var_dict, variable_definitions, processed_lines = {}, {}, []

    # Extract variable definitions
    for line in script_lines:
        if line.startswith('variable'):
            var_name, expr = parse_variable_line(line)
            if var_name and expr:
                variable_definitions[var_name] = expr
        else:
            processed_lines.append(line)

    # Extract dependencies between variables
    dependency_graph = {}
    for var, expr in variable_definitions.items():
        dependencies = set(re.findall(r'v_([a-zA-Z_]\w*)|\${([a-zA-Z_]\w*)}', expr))
        dependency_graph[var] = {v[0] or v[1] for v in dependencies if (v[0] or v[1]) in variable_definitions}

    # Resolve variables in topological order
    resolved_vars = set()
    while variable_definitions:
        progress_made = False
        for var_name, expr in list(variable_definitions.items()):
            # Only evaluate if all dependencies are resolved
            if dependency_graph[var_name].issubset(resolved_vars):
                expr = re.sub(r'v_([a-zA-Z_]\w*)|\${([a-zA-Z_]\w*)}', lambda m: str(var_dict.get(m.group(1) or m.group(2), f'v_{m.group(1) or m.group(2)}')), expr)
                expr = expr.replace('^', '**').replace('sqrt(', 'math.sqrt(')

                try:
                    result = simpleeval.simple_eval(expr, names={"pi": math.pi}, functions={"sqrt": math.sqrt})
                    if isinstance(result, float) and result.is_integer():
                        result = int(result)
                    var_dict[var_name] = str(result)
                    resolved_vars.add(var_name)
                    del variable_definitions[var_name]
                    progress_made = True
                except (NameError, SyntaxError, TypeError) as e:
                    continue  # Skip if an undefined variable is encountered

        if not progress_made:
            break  # Prevent infinite loops

    # Replace variables in the script
    new_lines = []
    for line in processed_lines:
        line = re.sub(r'v_([a-zA-Z_]\w*)|\${([a-zA-Z_]\w*)}', lambda m: str(var_dict.get(m.group(1) or m.group(2), f'v_{m.group(1) or m.group(2)}')), line)
        new_lines.append(line)

    return '\n'.join(new_lines)

def evaluate_expressions(script):
    """Evaluates only pure numeric expressions in the script."""
    arithmetic_pattern = re.compile(r'^[\d+\-*/().eE]+$')  # Optimized regex

    def evaluate_token(token):
        if arithmetic_pattern.fullmatch(token):  # Check if the token is a pure expression
            try:
                value = simpleeval.simple_eval(token.replace('^', '**'), names={"pi": math.pi}, functions={"sqrt": math.sqrt})
                if isinstance(value, float) and value.is_integer():
                    value = int(value)
                return str(value)
            except:
                pass  # Leave token unchanged if evaluation fails
        return token  # Return unchanged if not numeric

    return '\n'.join(
        " ".join(evaluate_token(token) for token in line.split())
        for line in script.splitlines()
    )

def evaluate_lammps_arithmetic(script):
    """
    Replace LAMMPS-style $( … ) expressions that are *purely numeric*
    with their evaluated values.
    """
    # matches $(   3.14*1e2  )  but *not* $(x+1) or $(v_t+1)
    expr_pat = re.compile(
        r"""\$\(\s*([0-9+\-*/^(). eE]+?)\s*\)""",  # capture inner arithmetic
        flags=re.VERBOSE,
    )

    def repl(match: re.Match) -> str:
        expr = match.group(1).replace("^", "**")
        try:
            value = simpleeval.simple_eval(expr, names={"pi": math.pi}, functions={"sqrt": math.sqrt})
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            return str(value)
        except Exception:
            # If evaluation fails (e.g., empty or invalid), leave it unchanged
            return match.group(0)

    return expr_pat.sub(repl, script)

def expand_loops(script):
    """Expands simple LAMMPS loops by evaluating 'if' conditions and unrolling iterations."""
    lines = script.splitlines()
    expanded_lines = []
    loop_label, loop_var_name, loop_count = None, None, None

    # **Step 1: Detect loop structure**
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('label '):
            loop_label = stripped.split()[1]
        elif stripped.startswith('variable ') and ' loop ' in stripped:
            parts = stripped.split()
            if len(parts) >= 4 and parts[2] == 'loop' and parts[3].isdigit():
                loop_var_name, loop_count = parts[1], int(parts[3])

    # **Step 2: Return early if no loop is detected**
    if not loop_var_name or not loop_count:
        return script  # No loop to expand

    # **Step 3: Expand loop iterations**
    for iteration in range(1, loop_count + 1):
        for line in lines:
            stripped = line.strip()

            # Skip loop control statements
            if stripped.startswith(f'variable {loop_var_name} loop') or \
               stripped.startswith(f'next {loop_var_name}') or \
               stripped.startswith(f'jump SELF {loop_label}'):
                continue

            # Process `if` conditions
            if stripped.startswith('if '):
                match = re.match(r'^if\s+"([^"]+)"\s+then\s+(.*)$', stripped)
                if match:
                    condition, then_part = match.groups()
                    condition_eval = condition.replace(f'${{{loop_var_name}}}', str(iteration))

                    if re.fullmatch(r'[\d\s<>=!]+', condition_eval):  # Ensure safe evaluation
                        try:
                            if simpleeval.simple_eval(condition_eval):
                                expanded_lines.extend(re.findall(r'"([^"]*)"', then_part))
                        except:
                            pass
                    continue  # Skip adding the original `if` line

            # Append regular lines
            expanded_lines.append(line)

    return '\n'.join(expanded_lines)

def sanitize(script):
    """Runs all sanitization steps in order, ensuring proper variable resolution and trailing newline."""
    script = remove_comments(script)
    script = remove_prints(script)
    script = merge_ampersand_lines(script)
    script = expand_loops(script)
    script = process_and_evaluate_variables(script)
    script = evaluate_expressions(script)
    script = evaluate_lammps_arithmetic(script)
    
    return script.rstrip() + '\n'