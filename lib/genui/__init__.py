"""GenUI form configuration, rendering, and response helpers.

GenUI is an interaction layer: it collects user choices visually, then the
agent reviews the resulting ui_response before writing canonical artifacts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

from schemas.artifacts import validate_artifact


FORM_DIRNAME = "ui"


@dataclass(frozen=True)
class FormBundle:
    """Materialized form files for one project interaction gate."""

    config: dict[str, Any]
    config_path: Path
    html_path: Path
    response_path: Path
    state_path: Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")


def validate_config(config: dict[str, Any]) -> None:
    """Validate a GenUI form config artifact."""
    validate_artifact("ui_form_config", config)


def validate_response(response: dict[str, Any]) -> None:
    """Validate a GenUI response artifact."""
    validate_artifact("ui_response", response)


def resolve_project_path(project_dir: Path | str, path: Path | str) -> Path:
    """Resolve path under project_dir and reject traversal outside the project."""
    project_root = Path(project_dir).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(project_root)
    except ValueError as exc:
        raise ValueError(f"Path {candidate} is outside project directory {project_root}") from exc
    return candidate


def _field_default(field: dict[str, Any]) -> Any:
    if "default" in field:
        return field["default"]
    field_type = field.get("type")
    if field_type == "multiselect":
        return []
    if field_type == "checkbox":
        return False
    return ""


def _render_help(field: dict[str, Any]) -> str:
    parts: list[str] = []
    if field.get("recommended"):
        parts.append(f"<p class=\"recommendation\">Recommended: {escape(str(field['recommended']))}</p>")
    if field.get("help_text"):
        parts.append(f"<p class=\"help\">{escape(str(field['help_text']))}</p>")
    return "\n".join(parts)


def _render_choices(field: dict[str, Any], *, as_radio: bool) -> str:
    input_type = "radio" if as_radio else "checkbox"
    current = _field_default(field)
    current_values = set(current if isinstance(current, list) else [current])
    rows: list[str] = []
    for choice in field.get("choices") or []:
        value = str(choice["value"])
        checked = " checked" if value in current_values else ""
        recommended = " <span class=\"badge\">recommended</span>" if choice.get("recommended") else ""
        description = ""
        if choice.get("description"):
            description = f"<span class=\"choice-description\">{escape(str(choice['description']))}</span>"
        rows.append(
            "<label class=\"choice\">"
            f"<input type=\"{input_type}\" name=\"{escape(field['id'], quote=True)}\" "
            f"value=\"{escape(value, quote=True)}\"{checked}>"
            f"<span>{escape(str(choice['label']))}{recommended}{description}</span>"
            "</label>"
        )
    return "<div class=\"choices\">\n" + "\n".join(rows) + "\n</div>"


def _render_field(field: dict[str, Any]) -> str:
    field_id = field["id"]
    field_type = field["type"]
    label = escape(str(field["label"]))
    required = " required" if field.get("required") else ""
    placeholder = escape(str(field.get("placeholder", "")), quote=True)
    value = _field_default(field)
    safe_id = escape(field_id, quote=True)
    help_html = _render_help(field)

    if field_type == "info_card":
        return f"<section class=\"info-card\"><h3>{label}</h3>{help_html}</section>"

    control = ""
    if field_type in {"text", "file_path"}:
        control = (
            f"<input name=\"{safe_id}\" type=\"text\" value=\"{escape(str(value), quote=True)}\" "
            f"placeholder=\"{placeholder}\"{required}>"
        )
    elif field_type == "url":
        control = (
            f"<input name=\"{safe_id}\" type=\"url\" value=\"{escape(str(value), quote=True)}\" "
            f"placeholder=\"{placeholder}\"{required}>"
        )
    elif field_type == "number":
        min_attr = f" min=\"{escape(str(field['min']), quote=True)}\"" if "min" in field else ""
        max_attr = f" max=\"{escape(str(field['max']), quote=True)}\"" if "max" in field else ""
        control = (
            f"<input name=\"{safe_id}\" type=\"number\" value=\"{escape(str(value), quote=True)}\""
            f"{min_attr}{max_attr}{required}>"
        )
    elif field_type == "textarea":
        control = f"<textarea name=\"{safe_id}\" placeholder=\"{placeholder}\"{required}>{escape(str(value))}</textarea>"
    elif field_type == "select":
        options = []
        for choice in field.get("choices") or []:
            selected = " selected" if str(choice["value"]) == str(value) else ""
            options.append(
                f"<option value=\"{escape(str(choice['value']), quote=True)}\"{selected}>"
                f"{escape(str(choice['label']))}</option>"
            )
        control = f"<select name=\"{safe_id}\"{required}>\n" + "\n".join(options) + "\n</select>"
    elif field_type == "radio":
        control = _render_choices(field, as_radio=True)
    elif field_type == "multiselect":
        control = _render_choices(field, as_radio=False)
    elif field_type in {"checkbox", "approval"}:
        checked = " checked" if bool(value) else ""
        control = f"<label class=\"choice\"><input name=\"{safe_id}\" type=\"checkbox\" value=\"true\"{checked}{required}> <span>Confirm</span></label>"
    else:
        control = f"<input name=\"{safe_id}\" type=\"text\" value=\"{escape(str(value), quote=True)}\"{required}>"

    return (
        f"<label class=\"field\" data-field-id=\"{safe_id}\" data-field-type=\"{escape(field_type, quote=True)}\">"
        f"<span class=\"field-label\">{label}</span>"
        f"{control}"
        f"{help_html}"
        "</label>"
    )


def render_form_html(config: dict[str, Any], *, submit_url: str = "/submit") -> str:
    """Render a self-contained HTML form for a GenUI config."""
    validate_config(config)
    fields = [
        {"id": field["id"], "type": field["type"]}
        for section in config["sections"]
        for field in section.get("fields", [])
    ]
    fields_json = json.dumps(fields).replace("</", "<\\/")
    title = escape(str(config["title"]))
    description = escape(str(config.get("description", "")))
    sections: list[str] = []
    for section in config["sections"]:
        rendered_fields = "\n".join(_render_field(field) for field in section.get("fields", []))
        section_desc = ""
        if section.get("description"):
            section_desc = f"<p class=\"section-description\">{escape(str(section['description']))}</p>"
        sections.append(
            "<section class=\"section\">"
            f"<h2>{escape(str(section['title']))}</h2>"
            f"{section_desc}"
            f"{rendered_fields}"
            "</section>"
        )

    actions = []
    for action in config["submit_actions"]:
        recommended = " recommended" if action.get("recommended") else ""
        actions.append(
            f"<button type=\"button\" class=\"action{recommended}\" "
            f"onclick=\"submitGenUI('{escape(action['kind'], quote=True)}')\">"
            f"{escape(str(action['label']))}</button>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    body {{ margin: 0; background: #f6f7f9; color: #111827; }}
    main {{ width: min(1040px, calc(100vw - 32px)); margin: 32px auto; }}
    header {{ margin-bottom: 24px; }}
    h1 {{ margin: 0 0 8px; font-size: 30px; font-weight: 760; letter-spacing: 0; }}
    h2 {{ margin: 0 0 10px; font-size: 18px; letter-spacing: 0; }}
    p {{ line-height: 1.5; }}
    .subtitle, .section-description {{ color: #526071; margin: 0 0 16px; }}
    .section {{ background: #ffffff; border: 1px solid #dce2ea; border-radius: 8px; padding: 20px; margin-bottom: 16px; }}
    .field {{ display: block; margin: 18px 0; }}
    .field-label {{ display: block; font-weight: 700; margin-bottom: 8px; }}
    input, textarea, select {{ box-sizing: border-box; width: 100%; border: 1px solid #b8c2cf; border-radius: 6px; padding: 11px 12px; font: inherit; background: #ffffff; color: #111827; }}
    textarea {{ min-height: 108px; resize: vertical; }}
    input:focus, textarea:focus, select:focus {{ outline: 2px solid #2563eb; outline-offset: 1px; border-color: #2563eb; }}
    .help, .recommendation {{ margin: 8px 0 0; color: #526071; font-size: 14px; }}
    .recommendation {{ color: #0f766e; font-weight: 650; }}
    .choices {{ display: grid; gap: 10px; }}
    .choice {{ display: flex; gap: 10px; align-items: flex-start; border: 1px solid #dce2ea; border-radius: 8px; padding: 11px 12px; background: #fbfcfe; }}
    .choice input {{ width: auto; margin-top: 4px; }}
    .choice-description {{ display: block; color: #526071; font-size: 14px; margin-top: 2px; }}
    .badge {{ color: #0f766e; font-size: 12px; font-weight: 750; margin-left: 6px; text-transform: uppercase; }}
    .info-card {{ border: 1px solid #b8c2cf; border-radius: 8px; background: #f8fafc; padding: 14px; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 10px; justify-content: flex-end; position: sticky; bottom: 0; padding: 16px 0; background: #f6f7f9; }}
    button.action {{ border: 1px solid #1f2937; background: #ffffff; color: #111827; border-radius: 6px; padding: 10px 14px; font: inherit; font-weight: 700; cursor: pointer; }}
    button.recommended {{ background: #111827; color: #ffffff; }}
    #status {{ min-height: 22px; color: #0f766e; font-weight: 650; }}
    @media (max-width: 640px) {{ main {{ width: min(100vw - 20px, 1040px); margin: 20px auto; }} .section {{ padding: 16px; }} .actions {{ justify-content: stretch; }} button.action {{ flex: 1 1 100%; }} }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>{title}</h1>
    <p class="subtitle">{description}</p>
  </header>
  <form id="genui-form">
    {''.join(sections)}
    <div id="status" role="status"></div>
    <div class="actions">
      {''.join(actions)}
    </div>
  </form>
</main>
<script>
const GENUI_FIELDS = {fields_json};
const SUBMIT_URL = {json.dumps(submit_url)};
async function submitGenUI(action) {{
  const form = document.getElementById('genui-form');
  const formData = new FormData(form);
  const values = {{}};
  for (const field of GENUI_FIELDS) {{
    if (field.type === 'multiselect') {{
      values[field.id] = formData.getAll(field.id);
    }} else if (field.type === 'checkbox' || field.type === 'approval') {{
      values[field.id] = formData.has(field.id);
    }} else {{
      values[field.id] = formData.get(field.id) || '';
    }}
  }}
  const payload = {{ action, values, browser_events: [] }};
  const status = document.getElementById('status');
  try {{
    const response = await fetch(SUBMIT_URL, {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify(payload)
    }});
    if (!response.ok) throw new Error(await response.text());
    status.textContent = 'Submitted. Return to the agent to continue.';
  }} catch (error) {{
    status.textContent = 'Submission failed: ' + error.message;
    status.style.color = '#b91c1c';
  }}
}}
</script>
</body>
</html>
"""


def _iter_fields(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        field
        for section in config.get("sections", [])
        for field in section.get("fields", [])
    ]


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list):
        return len(value) == 0
    if isinstance(value, bool):
        return value is False
    return False


def _validate_submission_values(config: dict[str, Any], submission: dict[str, Any]) -> None:
    """Validate browser-submitted values against configured form fields."""
    configured_actions = {action["kind"] for action in config.get("submit_actions", [])}
    action = submission.get("action", "submit")
    if action not in configured_actions:
        raise ValueError(f"Submit action {action!r} is not configured for {config['config_id']}")

    values = submission.get("values") or {}
    if not isinstance(values, dict):
        raise ValueError("GenUI submission values must be an object")

    configured_field_ids = {
        field["id"]
        for field in _iter_fields(config)
        if field.get("type") != "info_card"
    }
    unconfigured_field_ids = sorted(set(values) - configured_field_ids)
    if unconfigured_field_ids:
        raise ValueError(
            "GenUI submission contains values for fields that are not configured: "
            f"{unconfigured_field_ids}"
        )

    for field in _iter_fields(config):
        field_id = field["id"]
        field_type = field["type"]
        if field_type == "info_card":
            continue

        value = values.get(field_id)
        if field.get("required") and _is_empty(value):
            raise ValueError(f"Required GenUI field {field_id!r} is missing")

        choices = field.get("choices") or []
        if choices and not _is_empty(value):
            allowed = {choice["value"] for choice in choices}
            if field_type == "multiselect":
                if not isinstance(value, list):
                    raise ValueError(f"GenUI field {field_id!r} must be a list")
                invalid = [item for item in value if item not in allowed]
                if invalid:
                    raise ValueError(f"GenUI field {field_id!r} has invalid choices: {invalid}")
            elif value not in allowed:
                raise ValueError(f"GenUI field {field_id!r} has invalid choice: {value!r}")

        if field_type == "number" and not _is_empty(value):
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"GenUI field {field_id!r} must be numeric") from exc
            if "min" in field and number < field["min"]:
                raise ValueError(f"GenUI field {field_id!r} is below minimum {field['min']}")
            if "max" in field and number > field["max"]:
                raise ValueError(f"GenUI field {field_id!r} is above maximum {field['max']}")


def response_payload_from_submission(
    config: dict[str, Any],
    submission: dict[str, Any],
    *,
    response_id: str | None = None,
) -> dict[str, Any]:
    """Build a ui_response payload from browser-submitted values."""
    validate_config(config)
    _validate_submission_values(config, submission)
    action = submission.get("action", "submit")
    response = {
        "version": "1.0",
        "response_id": response_id or f"resp-{config['config_id']}-{int(datetime.now(timezone.utc).timestamp())}",
        "config_id": config["config_id"],
        "project_id": config["project_id"],
        "pipeline_type": config["pipeline_type"],
        "stage": config["stage"],
        "gate": config["gate"],
        "submitted_at": _now_iso(),
        "action": action,
        "values": submission.get("values") or {},
        "browser_events": submission.get("browser_events") or [],
        "validation": {"status": "pending", "errors": []},
    }
    validate_response(response)
    return response


def write_response(response_path: Path | str, response: dict[str, Any]) -> Path:
    """Write a validated ui_response artifact to disk."""
    validate_response(response)
    path = Path(response_path)
    _dump_json(path, response)
    return path


def write_form_bundle(project_dir: Path | str, config: dict[str, Any]) -> FormBundle:
    """Validate and materialize a GenUI form config plus static HTML preview."""
    validate_config(config)
    project_root = Path(project_dir)
    config_id = config["config_id"]
    base = resolve_project_path(project_root, Path("artifacts") / FORM_DIRNAME / config_id)
    config_path = base / "config.json"
    html_path = base / "form.html"
    response_path = base / "response.json"
    state_path = base / "server.json"

    _dump_json(config_path, config)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    with open(html_path, "w") as f:
        f.write(render_form_html(config))

    return FormBundle(
        config=config,
        config_path=config_path,
        html_path=html_path,
        response_path=response_path,
        state_path=state_path,
    )


__all__ = [
    "FormBundle",
    "render_form_html",
    "resolve_project_path",
    "response_payload_from_submission",
    "validate_config",
    "validate_response",
    "write_form_bundle",
    "write_response",
]
