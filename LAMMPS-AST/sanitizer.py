
import re
import math

def remove_comments(script):
    """Removes inline comments while preserving meaningful lines."""
    return '\n'.join(line.split('#', 1)[0].rstrip() for line in script.splitlines() if line.split('#', 1)[0].strip())

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
    tokens = line.split(maxsplit=4)

    if len(tokens) < 4 or tokens[0] != "variable":
        return None, None

    if tokens[2] == "equal":
        return tokens[1], tokens[3] if len(tokens) == 4 else tokens[3] + ' ' + tokens[4]
    
    if len(tokens) >= 5 and tokens[3] == "equal":
        return f"{tokens[1]}_{tokens[2]}", tokens[4]

    return None, None

def process_and_evaluate_variables(script):
    """Replaces variables (`${var}` and `v_var`) while ensuring dependencies are handled."""
    script_lines = script.splitlines()
    var_dict, variable_definitions, processed_lines = {}, {}, []

    # **Step 1: Extract variable definitions**
    for line in script_lines:
        if line.startswith('variable'):
            var_name, expr = parse_variable_line(line)
            if var_name and expr:
                variable_definitions[var_name] = expr
        else:
            processed_lines.append(line)

    # **Step 2: Resolve variable expressions iteratively**
    def replace_var(match):
        var_name = match.group(1) or match.group(2)  # Handles both v_var and ${var}
        return str(var_dict.get(var_name, f'v_{var_name}'))  # Keep unresolved as-is

    resolved = True
    while resolved and variable_definitions:
        resolved = False
        for var_name, expr in list(variable_definitions.items()):
            # Replace known variables inside the expression
            expr = re.sub(r'v_([a-zA-Z_]\w*)|\${([a-zA-Z_]\w*)}', replace_var, expr)

            # Convert LAMMPS operators to Python-compatible
            expr = expr.replace('^', '**').replace('sqrt(', 'math.sqrt(')

            try:
                var_dict[var_name] = str(eval(expr, {"__builtins__": None}, {"math": math}))
                del variable_definitions[var_name]
                resolved = True  # Continue resolving
            except:
                continue  # Skip variables that cannot be resolved yet

    # **Step 3: Replace variables in the script**
    new_lines = []
    for line in processed_lines:
        line = re.sub(r'v_([a-zA-Z_]\w*)|\${([a-zA-Z_]\w*)}', replace_var, line)
        new_lines.append(line)

    return '\n'.join(new_lines)

def evaluate_expressions(script):
    """Evaluates only pure numeric expressions in the script."""
    arithmetic_pattern = re.compile(r'^[\d+\-*/().eE]+$')  # Optimized regex
    math_safe = {"math": math, "__builtins__": None}

    def evaluate_token(token):
        if arithmetic_pattern.fullmatch(token):  # Check if the token is a pure expression
            try:
                return str(eval(token.replace('^', '**'), math_safe))  # Safe evaluation
            except:
                pass  # Leave token unchanged if evaluation fails
        return token  # Return unchanged if not numeric

    return '\n'.join(
        " ".join(evaluate_token(token) for token in line.split())
        for line in script.splitlines()
    )

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
                            if eval(condition_eval, {"__builtins__": None}):  # Secure eval
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
    script = merge_ampersand_lines(script)
    script = expand_loops(script)
    script = process_and_evaluate_variables(script)
    script = evaluate_expressions(script)
    
    return script.rstrip() + '\n'