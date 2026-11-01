from __future__ import annotations

from pathlib import Path

from clonway_cockpit.persona import load_persona
from clonway_cockpit.persona_soul import compose_system_prompt, load_soul

ROOT = Path(__file__).resolve().parent.parent


def test_gareth_persona_and_soul_load():
    persona = load_persona(ROOT / "config/personas/gareth.toml")
    assert persona.handle == "gareth" and persona.name == "Gareth"
    prompt = compose_system_prompt(load_soul(ROOT / "config/souls/gareth.md"))
    assert "never send an email" in prompt.lower()
    assert "resident or family calls" in prompt
    assert "never record a price" in prompt.lower()
