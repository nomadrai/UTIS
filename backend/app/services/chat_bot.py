"""Chat bot brain (task #11): system prompt, tools, executor loop.

The grounding contract (PLAN.md Phase-2 notes, inherited from
docs/METHODOLOGY.md):
    - The LLM INTERPRETS pre-computed summaries; it never computes numbers.
    - Any number it states must come from a tool result in this conversation.
    - What-if questions MUST go through the `run_scenario` tool (the fitted
      equation + baselines live server-side; LLM arithmetic is forbidden).
    - The methodology caveats are part of the system prompt verbatim so the
      bot inherits the project's intellectual honesty.

Tools call the ANALYSIS layer directly (etl.analysis / the same functions
the HTTP endpoints wrap) — no new analysis logic lives here. Tool results
are compacted (fields dropped, lists capped) so a full multi-tool
conversation still fits a free-tier context window.
"""

from __future__ import annotations

import json

from backend.config import settings
from backend.etl.analysis import hotspots as hotspots_analysis
from backend.etl.analysis import lst_stats, scenario
from backend.app.services import chat_providers

# ---------------------------------------------------------------------------
# Tools: schemas (OpenAI tool-call format)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_ward_year_stats",
            "description": (
                "Per-ward statistics for one analysis layer and one year: "
                "mean value per ward (lst in Kelvin, ndvi/ndbi as indices), "
                "within-year percentile rank (hotspot_pct, 0-100), city "
                "summary, plus precomputed hottest/coolest 5 wards. "
                "Available years: 2019-2025 (pre-monsoon). Use for trends "
                "(call per year), ward lookups, and city overviews."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "layer": {"type": "string", "enum": ["lst", "ndvi", "ndbi"]},
                    "year": {"type": "integer", "minimum": 2019, "maximum": 2025},
                },
                "required": ["layer", "year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_hotspots",
            "description": (
                "Persistent hotspot wards: within-year top-percentile "
                "hottest in MOST study years (2019-2025). Returns ward "
                "numbers, persistence fraction, years hot, mean percentile "
                "and mean LST, ranked hottest-first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pct": {
                        "type": "integer",
                        "minimum": 50,
                        "maximum": 99,
                        "description": "within-year percentile threshold (default 90)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_landcover",
            "description": (
                "ESA WorldCover 2021 land-cover class shares per ward: "
                "dominant class, built-up %, and top-3 classes. "
                "Single-year snapshot (2021) — the ONLY land-cover source."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_scenario",
            "description": (
                "REQUIRED for any what-if question ('what if ward X adds "
                "20% vegetation'). Runs the fitted regression "
                "dLST ~ dNDVI + dNDBI for one zone and returns the "
                "estimated surface-temperature change (est_lst_change_c, "
                "degrees Celsius) plus fit diagnostics. zone_id: 'city' or "
                "a ward number as a string. veg_delta / builtup_delta: "
                "PERCENT change of that zone's baseline, each in [-50, 50]."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "zone_id": {"type": "string", "description": "'city' or ward number e.g. '15'"},
                    "veg_delta": {"type": "number", "minimum": -50, "maximum": 50},
                    "builtup_delta": {"type": "number", "minimum": -50, "maximum": 50},
                },
                "required": ["zone_id", "veg_delta", "builtup_delta"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool executor: thin calls into the analysis layer, compacted results
# ---------------------------------------------------------------------------

def _compact_year_stats(layer: str, year: int) -> dict:
    payload = lst_stats.compute_yearly_stats([year], lst_stats.DEFAULT_SEASON, layer=layer)
    bundle = payload["years"].get(str(year))
    if bundle is None:
        return {"error": f"no data for {layer} {year}"}
    wards = [w for w in bundle["wards"] if w.get("mean") is not None]
    wards.sort(key=lambda w: w["mean"], reverse=True)
    return {
        "layer": layer,
        "year": year,
        "units": payload["units"],
        "city": bundle["city"],
        "hottest_5": wards[:5],
        "coolest_5": wards[-5:][::-1],
        "wards": [
            {"ward_no": w["ward_no"], "mean": w["mean"], "hotspot_pct": w.get("hotspot_pct")}
            for w in wards
        ],
    }


def _compact_hotspots(pct: int) -> dict:
    result = hotspots_analysis.detect_hotspots(
        lst_stats.DEFAULT_SEASON, pct, hotspots_analysis.DEFAULT_MIN_YEAR_FRAC
    )
    return {
        "rule": f"within-year top-{result['pct']}% percentile in >= {result['min_year_frac']} of years",
        "years_used": result["years_used"],
        "n_hotspots": len(result["hotspots"]),
        "hotspots": [
            {
                "ward_no": h["ward_no"],
                "persistence": h["persistence"],
                "years_hot": h["years_hot"],
                "mean_percentile": h["mean_percentile"],
                "mean_lst_k": h["mean_lst_k"],
            }
            for h in result["hotspots"][:15]
        ],
    }


def _compact_landcover() -> dict:
    # Same cache the /api/landcover-stats endpoint serves.
    from backend.app.api.landcover_stats import STATS_PATH

    if not STATS_PATH.exists():
        return {"error": "worldcover ward stats not computed — run: python -m backend.etl.gee_pulls.pull_worldcover --zonal-stats"}
    payload = json.loads(STATS_PATH.read_text())
    wards = []
    for w in payload.get("wards", []):
        if not w.get("dominant"):
            continue
        shares = w.get("shares", {})
        top3 = sorted(shares.items(), key=lambda kv: kv[1], reverse=True)[:3]
        wards.append({
            "ward_no": w.get("ward_no"),
            "dominant": w["dominant"],
            "built_up_pct": shares.get(50),
            "top3": [{"class": payload["classes"].get(int(k), k), "pct": v} for k, v in top3],
        })
    return {
        "snapshot_year": payload.get("year"),
        "classes": payload.get("classes"),
        "wards": wards,
    }


def execute_tool(name: str, args: dict) -> str:
    """Run one tool call; return a compact JSON string for the model.

    Errors are returned as JSON (not raised) so the model can read the
    reason and adjust instead of the loop crashing.
    """
    try:
        if name == "get_ward_year_stats":
            layer = str(args["layer"]).lower()
            if layer not in ("lst", "ndvi", "ndbi"):
                return json.dumps({"error": f"unknown layer {layer!r}"})
            return json.dumps(_compact_year_stats(layer, int(args["year"])))

        if name == "get_hotspots":
            return json.dumps(_compact_hotspots(int(args.get("pct", 90))))

        if name == "get_landcover":
            return json.dumps(_compact_landcover())

        if name == "run_scenario":
            zone_id = str(args["zone_id"])
            veg = float(args["veg_delta"])
            built = float(args["builtup_delta"])
            if not (-50 <= veg <= 50 and -50 <= built <= 50):
                return json.dumps({"error": "veg_delta/builtup_delta must be within [-50, 50]"})
            return json.dumps(scenario.predict(zone_id, veg, built, scenario.DEFAULT_SEASON))

        return json.dumps({"error": f"unknown tool {name!r}"})

    except FileNotFoundError as e:
        return json.dumps({"error": f"missing data: {e}"})
    except ValueError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:  # noqa: BLE001 — surfaced to the model as text
        return json.dumps({"error": f"{type(e).__name__}: {e}"})


# ---------------------------------------------------------------------------
# System prompt: METHODOLOGY digest (verbatim rules, honesty contract)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Nagpur Urban Heat Island assistant. You answer \
questions about land surface temperature (LST), vegetation (NDVI), built-up \
growth (NDBI), persistent hotspots, land cover, and what-if interventions \
for Nagpur's 114 wards, using pre-computed satellite analysis (2019-2025, \
pre-monsoon season; Landsat 8/9, Sentinel-2, ESA WorldCover 2021).

GROUNDING RULES (violating these is a wrong answer):
1. Every number you state MUST come from a tool result in this \
conversation. Never invent, estimate, or round beyond the source.
2. NEVER do arithmetic yourself. Any what-if ("what if ward 15 adds 20% \
vegetation") MUST go through the run_scenario tool — even if it looks \
trivial. State the tool's number, not your own.
3. Cite the source of key numbers inline, e.g. "(get_ward_year_stats lst \
2024)" or "(run_scenario ward 15)".
4. If a tool returns an error or empty data, say so plainly and suggest \
what to try — do not paper over it.

ANSWER STYLE:
- Lead with the direct answer in the first sentence.
- Then 2-5 short supporting points with the key numbers and ward names.
- When asked "what can be done", end with 1-3 physically sensible, \
locally actionable interventions (cool roofs, pavement de-sealing, pocket \
parks, tree canopy) tied to run_scenario results where they exist.
- Plain language, no data dumps: never list more than 5 wards unless \
explicitly asked for a table or ranking.

HONESTY CAVEATS (state when relevant, never hide):
- LST is SURFACE temperature, not the air temperature people feel.
- In the fitted scenario model, built-up change is the strong, statistically \
significant driver; the vegetation term is weak in this panel (year-to-year \
NDVI deltas are noisy) — present vegetation effects as indicative.
- Ward boundaries derive from a 2005 ward map with ~170 m edge uncertainty.
- "Hotspot" means persistently top-percentile across years, not a \
single-year heatwave.
"""


# ---------------------------------------------------------------------------
# The tool-calling loop
# ---------------------------------------------------------------------------

def run_chat(user_message: str, history: list[dict] | None = None) -> dict:
    """Full tool-calling loop for one user question.

    history: prior [{role, content}] turns (assistant-visible text only;
    tool internals are not persisted across requests).

    Returns {reply, sources, provider} — sources lists the tools whose
    results fed the answer (for UI chips).
    """
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": user_message})

    used_tools: list[str] = []
    payload: dict = {"messages": messages, "tools": TOOLS, "temperature": 0.3}

    for _round in range(max(1, int(settings.AI_MAX_TOOL_ROUNDS))):
        resp = chat_providers.chat_completion(payload)
        msg = resp["choices"][0]["message"]

        calls = msg.get("tool_calls") or []
        if not calls:
            return {
                "reply": msg.get("content") or "",
                "sources": used_tools,
                "provider": resp.get("_provider"),
            }

        # Append the assistant's tool-call turn, then every tool result.
        messages.append({
            "role": "assistant",
            "content": msg.get("content") or "",
            "tool_calls": calls,
        })
        for call in calls:
            fn = call.get("function", {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            used_tools.append(name)
            result = execute_tool(name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", ""),
                "content": result,
            })

    # Model kept calling tools past the cap — force a final no-tools answer.
    payload["messages"] = messages + [{
        "role": "user",
        "content": "Tool budget reached. Give your best answer NOW using the tool results above.",
    }]
    payload.pop("tools", None)
    resp = chat_providers.chat_completion(payload)
    return {
        "reply": resp["choices"][0]["message"].get("content") or "",
        "sources": used_tools,
        "provider": resp.get("_provider"),
    }
