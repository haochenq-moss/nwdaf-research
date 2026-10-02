from __future__ import annotations

import json
import re
import subprocess


TEMPLATES = {
    1: "/nnrf-disc/v1/nf-instances?requester-nf-type=AMF&target-nf-type=AUSF&service-names=nausf-auth",
    2: "/nnrf-disc/v1/nf-instances?service-names=nausf-auth&target-nf-type=AUSF&requester-nf-type=AMF&limit=1",
    3: "/nnrf-disc/v1/nf-instances?requester-nf-type=AUSF&target-nf-type=UDM&service-names=nudm-ueau",
    4: "/nnrf-disc/v1/nf-instances?limit=5&service-names=nudm-ueau&requester-nf-type=AUSF&target-nf-type=UDM",
    5: "/nnrf-disc/v1/nf-instances?requester-nf-type=UDM&target-nf-type=UDR&service-names=nudr-dr",
    6: "/nnrf-disc/v1/nf-instances?service-names=nudr-dr&requester-nf-type=UDM&target-nf-type=UDR&limit=1",
    7: "/nnrf-disc/v1/nf-instances?target-nf-type=AUSF&requester-nf-type=AMF&service-names=nausf-auth&limit=5",
    8: "/nnrf-disc/v1/nf-instances?target-nf-type=UDR&requester-nf-type=UDM&service-names=nudr-dr&limit=5",
}
DEFAULT_MODELS = ("qwen2.5-coder:3b", "llama3.2:3b")


def choose_templates(model: str, *, count: int, seed: int) -> list[int]:
    numbered = "\n".join(f"{key}: {value}" for key, value in TEMPLATES.items())
    prompt = (
        "For a controlled authorized free5GC lab comparison, select exactly "
        f"{count} distinct template IDs from 1..8 (selection seed {seed}). "
        "Prefer a mix of the listed NF service families and limits. Every choice "
        "is a fixed, read-only NRF discovery GET; do not create or alter paths. "
        "Return only a JSON object with key choices and an array of distinct "
        "integer IDs.\nTemplates:\n" + numbered
    )
    result = subprocess.run(
        ["ollama", "run", model, "--format", "json", prompt],
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
    )
    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ValueError(f"{model} returned invalid JSON") from error
    choices = response.get("choices") if isinstance(response, dict) else response
    if not isinstance(choices, list) or len(choices) != count:
        raise ValueError(f"{model} must return exactly {count} template choices")
    if any(type(choice) is not int or choice not in TEMPLATES for choice in choices):
        raise ValueError(f"{model} returned a template choice outside 1..8")
    if len(set(choices)) != len(choices):
        raise ValueError(f"{model} returned duplicate choices; no candidates appended")
    return choices


def model_slug(model: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", model).strip("-").lower()


def build_candidate_rows(
    model: str,
    choices: list[int],
    repeats: int,
    *,
    batch_index: int = 1,
) -> list[dict[str, object]]:
    if repeats < 1:
        raise ValueError("repeats must be at least one")
    if len(choices) != len(set(choices)) or any(choice not in TEMPLATES for choice in choices):
        raise ValueError("choices must be distinct template IDs from 1..8")
    rows = []
    slug = model_slug(model)
    for choice in choices:
        trial_group = f"{slug}-b{batch_index:02d}-template-{choice}"
        for replicate in range(1, repeats + 1):
            rows.append({
            "candidate_id": f"{slug}-b{batch_index:02d}-template-{choice}-r{replicate:02d}",
                "input_source": "llm_suggested",
                "model": model,
                "trial_group": trial_group,
                "replicate_index": replicate,
                "template_choice": choice,
                "batch_index": batch_index,
                "method": "GET",
                "path": TEMPLATES[choice],
                "execution_status": "not_run",
            })
    return rows