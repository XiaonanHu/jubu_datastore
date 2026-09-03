"""
Story generation assets shared by the pipeline and the library tooling.

    prompts/        the writing prompt the prose stage obeys (reviewed here)
    craft_gate.py   the mechanical rules: word ceilings, banned language,
                    paragraph and asterisk checks, braid/slot structure

The pipeline itself lives in jubu_backend (jubu_chat.story_generation) and
imports this package; the audit and ingest scripts in scripts/ import it
too. One copy of every rule.
"""
