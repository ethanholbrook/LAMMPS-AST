from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PIPELINE_DIR = Path(__file__).resolve().parent
SCRATCH_DIR = PIPELINE_DIR.parent
EVAL_ROOT = SCRATCH_DIR.parent
PUBLICATION_DIR = EVAL_ROOT / "publication"

load_dotenv(SCRATCH_DIR / ".env")


PROMPTS = {
    "prompt1": (
        "Method Description:\n\n"
        "We used molecular dynamics with LAMMPS to equilibrate an Al sample under "
        "isobaric, isothermal conditions (NPT ensemble) at 300 K and 1 atm for 500 ps. "
        "The initial conditions were obtained by replicating the fcc unit cell 5 times in "
        "each direction. We used Nose-Hoover thermostat and barostat with relaxation "
        "timescales of 0.1 and 1 ps, respectively. All MD simulations were performed using "
        "LAMMPS. Atomic interactions were obtained using an embedded atom model developed "
        "by Ercolessi and Adams [1] obtained from OpenKIM.org. [1] EAM alloy potential for "
        "Al developed by Ercolessi and Adams (1994) v002. OpenKIM. 2018. "
        "doi:10.25950/376e3e7e."
    ),
    "prompt2": (
        "Method Description:\n\n"
        "We characterized the melting of a bulk Ni sample using molecular dynamics with "
        "LAMMPS. The initial condition was obtained by replicating the Ni unit cell 10 times "
        "in each direction. Initial velocities were drawn from the Maxwell-Boltzmann "
        "distribution at 600 K. The system was heated from 300 K to 2500 K continuously, at a "
        "rate of 10 K per ps under isothermal and isobaric conditions at 1 atm. Interactions "
        "were described using an embedded atom model developed by Mishin et al. in 1999 [1] "
        "obtained from OpenKIM.org. [1] EAM potential (LAMMPS cubic hermite tabulation) for "
        "Ni developed by Mishin et al. (1999) v005. OpenKIM; 2018. doi:10.25950/a88dfc37."
    ),
    "prompt3": (
        "Method Description:\n\n"
        "We simulate spall failure on Nb single crystals using high-velocity impact simulations "
        "using molecular dynamics (MD) with the LAMMPS code. We simulate the impact of a "
        "projectile on a target with a relative velocity of 2 km/s. The projectile is obtained "
        "by replicating the Nb BCC unit cell 20 times along the [100], [010], and [001]; the "
        "target is longer along the shock direction and is obtained by replicating the BCC unit "
        "cell 20 times along [100] and [010] and 40 times along [001]. We apply periodic "
        "boundary conditions along the directions normal to the impact direction, [001], and "
        "free boundaries along [001]. A gap of 1.5 nm initially separates the target and "
        "projectile. The system is equilibrated at 300 K for 100 ps using isothermal, "
        "isochoric MD. An impact velocity of 2 km/s is added to the thermal velocities to all "
        "the atoms in the projectile along [001] in the direction of the target. Adiabatic MD "
        "is used to simulate the impact and subsequent expansion. All atomic interactions are "
        "described using an EAM potential developed by Fellinger et al. [1] and downloaded "
        "from openKIM [2]. [1] Fellinger MR, Park H, Wilkins JW. Force-matched embedded-atom "
        "method potential for niobium. Physical Review B. 2010 Apr;81(14):144119. "
        "doi:10.1103/PhysRevB.81.144119 [2] https://doi.org/10.25950/befb2eea."
    ),
}


SYSTEM_PROMPT = (
    "System Prompt:\n"
    "You are an expert in molecular dynamics simulations and LAMMPS scripting. "
    "Your task is to generate complete, runnable LAMMPS input scripts based only on "
    "the provided method description. You must follow strict formatting rules and "
    "proceed step by step, reasoning through each section logically before writing the "
    "final output. All reasoning should be internal. Do not display intermediate "
    "thoughts, summaries, or explanations. Only output the final script.\n\n"
    "Input Format:\n"
    "You will receive a user input labeled Method Description. This section contains all "
    "the experimental and simulation details.\n\n"
    "Workflow:\n"
    "Parse and interpret the method description carefully and extract only the information "
    "explicitly stated. Do not assume values or simulation parameters beyond what is given. "
    "Plan the LAMMPS input script structure using these sections: Initialization, System "
    "Construction, Potential, Miscellaneous if needed, and Production Run.\n\n"
    "Constraints:\n"
    "- Assume that a potential file named '../../../potentials/prompt1.potential' is "
    "available and ready to use.\n"
    "- Be specific with pair_style so it matches the potential format discussed.\n"
    "- Do not include any comments.\n"
    "- Explicitly define commands even when defaults would work.\n"
    "- Output a single clean script that is valid LAMMPS syntax and runnable without "
    "modification.\n"
    "- Do not include explanations, metadata, or commentary. Only output the final script."
)


OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.5")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-7")
TRIALS = int(os.getenv("LAMMPS_PIPELINE_TRIALS", "10"))

# List out models you wish to either generate or evaluate. 
MODELS = {OPENAI_MODEL: {
        "provider": "openai",
        "display_name": OPENAI_MODEL,
        "reasoning_effort": os.getenv("OPENAI_REASONING_EFFORT", "medium"),
    },} 

MODELS = {
    # OPENAI_MODEL: {
    #     "provider": "openai",
    #     "display_name": OPENAI_MODEL,
    #     "reasoning_effort": os.getenv("OPENAI_REASONING_EFFORT", "high"),
    # },
    # ANTHROPIC_MODEL: {
    #     "provider": "anthropic",
    #     "display_name": ANTHROPIC_MODEL,
    # },
    "gpt-4.1": {
        "provider": "openai",
        "display_name": "gpt-4.1",
    },
    "gpt-4o": {
        "provider": "openai",
        "display_name": "gpt-4o",
    },
    "gpt-5": {
        "provider": "openai",
        "display_name": "gpt-5",
        "reasoning_effort": os.getenv("OPENAI_REASONING_EFFORT", "medium"),
    },
    "gpt-o3": {
        "provider": "openai",
        "display_name": "gpt-o3",
        "reasoning_effort": os.getenv("OPENAI_REASONING_EFFORT", "medium"),
    },
    "claude-4-opus-20250514": {
        "provider": "anthropic",
        "display_name": "claude-4-opus-20250514",
    },
        "gpt-5.4": {
        "provider": "openai",
        "display_name": "gpt-5.4",
        "reasoning_effort": os.getenv("OPENAI_REASONING_EFFORT", "high"),
    },
    "claude-opus-4-7": {
        "provider": "anthropic",
        "display_name": "claude-opus-4-7",
    },
        "gpt-5.5": {
        "provider": "openai",
        "display_name": "gpt-5.5",
        "reasoning_effort": os.getenv("OPENAI_REASONING_EFFORT", "medium"),
    },
}


PROMPT_MODEL_MAP = {
    prompt: list(MODELS.keys())
    for prompt in PROMPTS
}


GENERATED_SCRIPTS_DIR = PUBLICATION_DIR / "generated_scripts"
PIPELINE_GENERATED_FILES_DIR = PUBLICATION_DIR / "pipeline_generated_files"
RAW_RESPONSES_DIR = PIPELINE_GENERATED_FILES_DIR / "raw_responses"
SANITIZED_SCRIPTS_DIR = PIPELINE_GENERATED_FILES_DIR / "sanitized_scripts"
ASTS_DIR = PIPELINE_GENERATED_FILES_DIR / "asts"
SHORT_RUN_SCRIPTS_DIR = PIPELINE_GENERATED_FILES_DIR / "short_run_scripts"
LOGS_DIR = PIPELINE_GENERATED_FILES_DIR / "logs"
PAIR_CHANGE_DIR = PIPELINE_GENERATED_FILES_DIR / "pair_change"
PAIR_CHANGE_LOGS_DIR = PIPELINE_GENERATED_FILES_DIR / "pair_change_logs"
ERRORS_DIR = PIPELINE_GENERATED_FILES_DIR / "errors"
LAMMPS_GENERATED_FILES_DIR = PIPELINE_GENERATED_FILES_DIR / "lammps_generated_files"

DATA_DIR = PIPELINE_GENERATED_FILES_DIR / "data"
PARSING_DF_PATH = DATA_DIR / "parsing_df.pkl"
FINAL_PAIR_DF_PATH = DATA_DIR / "final_pair_df.pkl"
ACCURACY_DF_PATH = DATA_DIR / "accuracy_df_trees.pkl"

RESULTS_DIR = PUBLICATION_DIR / "results"
SUMMARY_CSV_PATH = RESULTS_DIR / "summary_table.csv"
SUMMARY_MD_PATH = RESULTS_DIR / "summary_table.md"
SANKEY_HTML_PATH = RESULTS_DIR / "final_sankey.html"
SANKEY_PNG_PATH = RESULTS_DIR / "final_sankey.png"

POTENTIALS_DIR = PUBLICATION_DIR / "potentials"


DEFAULT_LAMMPS_EXECUTABLE = os.getenv(
    "LAMMPS_EXECUTABLE",
    "/apps/spack/gilbreth-r9/apps/lammps/20240829-gcc-11.5.0-bsocngl/bin/lmp",
)

MODEL_DISPLAY = {name: meta["display_name"] for name, meta in MODELS.items()}

STAGE_ORDER = [
    "generate",
    "parse",
    "execute",
    "accuracy",
    "summarize",
]
