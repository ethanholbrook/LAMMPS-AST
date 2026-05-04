# LAMMPS-AST Eval — Reference

## Pipeline stages and what each catches

| Stage | What it catches | Cost |
|---|---|---|
| Normalizer | Unresolvable variables, malformed loop constructs, bad `$(...)` expressions | Free |
| Parser | Invalid command names, wrong argument types, unsupported syntax | Free |
| Execution (10 steps) | Command ordering errors, missing files, runtime LAMMPS errors | Low |
| PSZ execution | Separates pair_style errors from other execution errors | Low |

## Common failure modes and fixes

### 1. Pair style mismatch (most frequent — ~30% of scripts)

**Symptoms:** Execution fails; PSZ run succeeds.

**Root cause:** EAM potentials have multiple LAMMPS variants (`eam`, `eam/alloy`, `eam/fs`) that differ in file format. LLMs frequently select the wrong variant.

**Fix pattern:**
- If prompt references a Mishin, Ercolessi-Adams, or single-element EAM potential → use `eam/alloy`
- If potential file has `.fs` extension → use `eam/fs`
- If using OpenKIM → use `pair_style kim` with the model name
- After PSZ success, fix only the `pair_style`/`pair_coeff` lines; leave the rest unchanged.

---

### 2. Malformed variable expressions (normalization failure)

**Symptoms:** Either `sanitized: false, sanitize_error: ...` (normalizer raised an exception) or `sanitized: false, unresolved_variables: [...]` (normalizer succeeded but left variable references that could not be resolved). The `unresolved_variables` list names each problematic reference.

**Root cause:** LLMs write variable expressions that cannot be resolved, e.g., referencing undefined variables or using LAMMPS thermo keywords (`v_temp`, `c_pe`) as arithmetic inputs. `sanitize()` does not always raise on unresolvable variables — it may leave them in the output, where they are detected by a subsequent pass.

**Fix pattern:** Replace unresolvable variable expressions with their intended literal numeric values based on the prompt description.

---

### 3. Hallucinated command arguments (parser failure)

**Symptoms:** `parsed: false`; error token is a keyword or style name.

**Common examples:**
- `velocity group add` — does not exist; use `velocity group set vx vy vz sum yes`
- Non-existent `fix` styles or `compute` styles
- Invalid `boundary` specifiers

**Fix pattern:** Check the error token against LAMMPS documentation. Replace with the correct syntax.

---

### 4. Incorrect unit handling (execution failure or silent inaccuracy)

**Symptoms:** Execution may succeed, but parameters are physically wrong.

**Common examples:**
- Velocity specified in m/s instead of Å/ps (units metal: 1 m/s = 0.01 Å/ps)
- Lattice parameter set to 1.0 Å instead of the physical value
- Timestep in wrong units

**Fix pattern:** For `units metal`: distances in Å, time in ps, velocity in Å/ps, energy in eV. Apply unit conversions explicitly. Check the units against LAMMPS documentation.

---

### 5. Region/group definition errors (parser or execution failure)

**Symptoms:** Parser error on `region` or `group` command, or LAMMPS runtime error about undefined groups.

**Common examples:**
- Referencing a group before it is defined
- Using `lattice` units in `region` when `lattice` command has not been called
- Reversed projectile/target geometry in impact simulations

**Fix pattern:** Ensure `lattice` is defined before any `region` using `units lattice`. Verify group names match exactly. Check command ordering (lattice → region → create_atoms → group).

---

### 6. Thermostat/barostat damping constants (silent inaccuracy)

**Symptoms:** Execution succeeds, but physical results are wrong.

**Common examples:**
- Damping set to 1 (LAMMPS default, often 100× too small)
- Temperature damping = pressure damping (should differ by ~10×)

**Recommended values (units metal):** temp damping = 0.1 ps, pressure damping = 1.0 ps.

---

## Grammar coverage

The `lammps-ast` parser covers ~62 LAMMPS command types. Commands outside this set will produce a parser error even if syntactically valid in LAMMPS. If a parse error occurs on a command you believe is valid, check whether it is in the supported set before attempting a fix.

Key supported commands: `units`, `boundary`, `dimension`, `atom_style`, `lattice`, `region`, `create_box`, `create_atoms`, `mass`, `pair_style`, `pair_coeff`, `bond_style`, `velocity`, `fix` (nve/nvt/npt/langevin), `run`, `minimize`, `dump`, `restart`, `variable`, `compute`, `group`, `thermo`, `timestep`, `read_data`, `write_data`, `replicate`, `change_box`, `delete_atoms`, `displace_atoms`.
