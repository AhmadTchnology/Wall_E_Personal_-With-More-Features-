"""
actions/tool_bridge.py — Gemini ↔ OpenAI tool format converter.

Converts the existing TOOL_DECLARATIONS (Gemini format) into
OpenAI function-calling format so NVIDIA NIM can use the same tools.
"""


# ── Gemini type → JSON Schema type mapping ────────────────

_TYPE_MAP = {
    "STRING":  "string",
    "INTEGER": "integer",
    "NUMBER":  "number",
    "BOOLEAN": "boolean",
    "ARRAY":   "array",
    "OBJECT":  "object",
}


def _convert_property(prop: dict) -> dict:
    """Convert a single Gemini property definition to JSON Schema."""
    schema = {}
    ptype = prop.get("type", "STRING")
    schema["type"] = _TYPE_MAP.get(ptype, "string")

    if "description" in prop:
        schema["description"] = prop["description"]

    # Handle ARRAY items
    if ptype == "ARRAY" and "items" in prop:
        items = prop["items"]
        schema["items"] = {"type": _TYPE_MAP.get(items.get("type", "STRING"), "string")}

    return schema


def gemini_to_openai_tools(gemini_declarations: list[dict]) -> list[dict]:
    """
    Convert a list of Gemini TOOL_DECLARATIONS to OpenAI function-calling format.

    Gemini format:
        {"name": ..., "description": ..., "parameters": {"type": "OBJECT", "properties": {...}, "required": [...]}}

    OpenAI format:
        {"type": "function", "function": {"name": ..., "description": ..., "parameters": {"type": "object", "properties": {...}, "required": [...]}}}
    """
    openai_tools = []

    for decl in gemini_declarations:
        params = decl.get("parameters", {})
        properties = {}

        for pname, pdef in params.get("properties", {}).items():
            properties[pname] = _convert_property(pdef)

        openai_func = {
            "type": "function",
            "function": {
                "name": decl["name"],
                "description": decl.get("description", ""),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": params.get("required", []),
                },
            },
        }
        openai_tools.append(openai_func)

    return openai_tools
