from __future__ import annotations

import os
import re
from pathlib import Path

import pipeline_config as cfg
from pipeline_common import build_trial_dataframe, ensure_directories, format_counts, print_model_lines, print_sample_status, append_stage_error, reset_stage_error_log


DEFAULT_DELIMITER_PATTERN = r"[-=]{10,}"


def extract_lammps_script(response_text: str, delimiter: str | None = None) -> str:
    code_blocks = re.findall(r"```(?:lammps|bash|[\w]*)?\n(.*?)\n```", response_text, re.DOTALL)
    
    # Code Block Extraction: Fenced Code
    if code_blocks:
        return code_blocks[0].strip()

    # Code Block Extraction: Delimiter-Based
    delimiter_pattern = delimiter or DEFAULT_DELIMITER_PATTERN
    match = re.search(rf"{delimiter_pattern}\n(.*?)\n{delimiter_pattern}", response_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    if delimiter is not None:
        raise ValueError(
            "Explicit delimiter extraction failed. "
            "Provide a delimiter description/pattern that matches the model output exactly."
        )

    # Code Block Extraction: Fallback to Full Response
    stripped = response_text.strip()
    if stripped:
        return stripped

    raise ValueError("No LAMMPS script found in model response.")


def write_script_file(
    prompt_name: str,
    model_name: str,
    trial: int,
    response_text: str,
    delimiter: str | None = None,
) -> Path:
    raw_dir = cfg.RAW_RESPONSES_DIR / prompt_name / model_name
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{prompt_name}-{model_name}-T{trial}.raw.txt"
    raw_path.write_text(response_text, encoding="utf-8")

    output_dir = cfg.GENERATED_SCRIPTS_DIR / prompt_name / model_name
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{prompt_name}-{model_name}-T{trial}.in"
    output_path.write_text(extract_lammps_script(response_text, delimiter=delimiter) + "\n", encoding="utf-8")
    return output_path


def _load_openai_client():
    api_key = os.getenv("OPENAI_API") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API or OPENAI_API_KEY for generation.")

    from openai import OpenAI

    return OpenAI(api_key=api_key)


def _load_anthropic_client():
    api_key = os.getenv("ANTHROPIC_API") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("Missing ANTHROPIC_API or ANTHROPIC_API_KEY for generation.")

    import anthropic

    return anthropic.Anthropic(api_key=api_key)


def generate_openai_response(client, model_name: str, prompt_text: str) -> str:
    kwargs = {
        "model": model_name,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": cfg.SYSTEM_PROMPT}]},
            {"role": "user", "content": [{"type": "input_text", "text": prompt_text}]},
        ],
    }
    reasoning_effort = cfg.MODELS[model_name].get("reasoning_effort")
    if reasoning_effort:
        kwargs["reasoning"] = {"effort": reasoning_effort}
    response = client.responses.create(**kwargs)
    return response.output_text


def generate_anthropic_response(client, model_name: str, prompt_text: str) -> str:
    response = client.messages.create(
        model=model_name,
        max_tokens=4096,
        system=cfg.SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt_text}],
    )
    return "".join(block.text for block in response.content if getattr(block, "type", None) == "text")


def generate_scripts(force: bool = False) -> list[Path]:
    ensure_directories()
    reset_stage_error_log("generate")
    written_paths: list[Path] = []
    openai_client = None
    anthropic_client = None

    for prompt_name, prompt_text in cfg.PROMPTS.items():
        for model_name, model_meta in cfg.MODELS.items():
            for trial in range(cfg.TRIALS):
                target_path = cfg.GENERATED_SCRIPTS_DIR / prompt_name / model_name / f"{prompt_name}-{model_name}-T{trial}.in"
                if target_path.exists() and not force:
                    written_paths.append(target_path)
                    print_sample_status("Generate", prompt_name, model_name, trial, "OK", "reused")
                    continue

                try:
                    if model_meta["provider"] == "openai":
                        openai_client = openai_client or _load_openai_client()
                        response_text = generate_openai_response(openai_client, model_name, prompt_text)
                    elif model_meta["provider"] == "anthropic":
                        anthropic_client = anthropic_client or _load_anthropic_client()
                        response_text = generate_anthropic_response(anthropic_client, model_name, prompt_text)
                    else:
                        raise ValueError(f"Unsupported provider: {model_meta['provider']}")

                    delimiter = model_meta.get("delimiter")
                    written_paths.append(
                        write_script_file(
                            prompt_name,
                            model_name,
                            trial,
                            response_text,
                            delimiter=delimiter,
                        )
                    )
                    print_sample_status("Generate", prompt_name, model_name, trial, "OK")
                except Exception as exc:
                    append_stage_error("generate", prompt_name, model_name, trial, str(exc))
                    print_sample_status("Generate", prompt_name, model_name, trial, "FAIL", str(exc))
                    raise

    return written_paths


def cli_generate() -> None:
    written = generate_scripts(force=False)
    print(f"Wrote or reused {len(written)} generated scripts.")
    print(
        format_counts(
            "Generation summary",
            [
                ("prompts", len(cfg.PROMPTS)),
                ("models", len(cfg.MODELS)),
                ("trials_per_combo", cfg.TRIALS),
                ("total_scripts", len(written)),
            ],
        )
    )
    generated_rows = build_trial_dataframe()
    print_model_lines(
        generated_rows,
        "Generation",
        lambda model_df: [
            ("scripts", len(model_df)),
            ("prompts", model_df["prompt"].nunique()),
            ("trials", cfg.TRIALS),
        ],
    )
