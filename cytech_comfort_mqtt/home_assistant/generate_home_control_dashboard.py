"""Generate a native Lovelace dashboard from the same CCLX definitions as the bridge."""
import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "rootfs" / "comfort2"))
import defusedxml.ElementTree as ET
from home_control_models import parse_home_control


def dashboard(controls, domain="cytech_comfort_mqtt"):
    if not re.fullmatch(r"[a-z0-9_]+", domain):
        raise ValueError("Dashboard entity IDs require a lowercase alphanumeric MQTT domain with underscores")
    views = []
    for group in sorted({c.group for c in controls.values()}):
        members = sorted((c for c in controls.values() if c.group == group), key=lambda c: c.key)
        cards = [{"type": "markdown", "content":
                  "Feedback updates from Comfort. **Unknown** means no feedback has arrived; "
                  "**Unavailable** means the bridge or panel is offline. Values are raw feedback, "
                  "not percentages. Pressing an action does not predict its result."}]
        for c in members:
            stem = f"{domain}_home_control_{group:02d}_{c.key:02d}"
            rows = []
            if c.has_feedback:
                rows.append({"entity": f"sensor.{stem}", "name": "Feedback"})
            rows.extend({"entity": f"button.{stem}_{a.number}", "name": a.label}
                        for a in c.actions)
            if rows:
                cards.append({"type": "entities", "title": c.label,
                              "show_header_toggle": False, "entities": rows})
            else:
                cards.append({"type": "markdown", "title": c.label,
                              "content": "No feedback or configured action entities."})
        views.append({"title": members[0].group_label or f"Group {group}",
                      "path": f"group-{group}", "icon": "mdi:home-automation", "cards": cards})
    if not views:
        views.append({"title": "Home Control", "path": "home", "cards": [
            {"type": "markdown", "content": "No Home Control definitions found in this CCLX."}]})
    return {"title": "Comfort Home Control", "views": views}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cclx", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--domain", default="cytech_comfort_mqtt")
    args = parser.parse_args()
    controls, errors = parse_home_control(ET.parse(args.cclx).getroot())
    if errors:
        parser.error("; ".join(errors))
    # JSON is valid YAML and can also be pasted into HA's raw dashboard editor.
    result = dashboard(controls, args.domain)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}: {len(controls)} controls across {len(result['views'])} views")


if __name__ == "__main__":
    main()
