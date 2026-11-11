"""CCLX Home Control definitions. No Home Assistant dependencies."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ControlAction:
    number: int
    label: str
    response: str
    response_number: int | None = None


@dataclass(frozen=True)
class Control:
    group: int
    key: int
    group_label: str
    label: str
    feedback_type: str
    feedback_name: str
    actions: tuple = ()
    feedback_number: int | None = None

    @property
    def has_feedback(self):
        return self.feedback_type.lower() not in ("", "none", "x10")


def phrase(element):
    return (element.get("AlternativePhrase", "").strip() or
            " ".join(element.get(f"PhraseWord{i}", "").strip() for i in range(1, 5)).strip())


def parse_home_control(root):
    controls, diagnostics = {}, []
    for group in root.findall("./ControlMenuGroups/ControlMenuGroup"):
        for item in group.findall("./ControlMenuItems/ControlMenuItem"):
            try:
                g, k = int(group.get("Number", "")), int(item.get("Number", ""))
                if not 0 <= g <= 5 or not 0 <= k <= 9 or (g, k) in controls:
                    raise ValueError("invalid or duplicate address")
                feedback = item.get("FeedbackType", "None")
                if feedback.lower() == "x10":
                    continue
                actions = []
                seen = set()
                for sub in item.findall("./ControlMenuSubItems/ControlMenuSubItem"):
                    label, response = phrase(sub), sub.get("ResponseName", "")
                    if not label and not response:
                        continue
                    number = int(sub.get("Number", ""))
                    if not 0 <= number <= 9 or number in seen:
                        raise ValueError("invalid or duplicate action")
                    seen.add(number)
                    target = next((r for r in root.findall("./Responses/Response") if r.get("Name") == response), None)
                    # Exclude obsolete X10 responses from this new integration.
                    if target is not None and any("X10" in (s.text or "").upper() for s in target.iter("string")):
                        continue
                    actions.append(ControlAction(number, label or response, response,
                                                 int(target.get("Number")) if target is not None else None))
                label = phrase(item)
                feedback_name = item.get("FeedbackName", "")
                tag = {"counter": "Counter", "sensor": "SensorResponse", "flag": "Flag",
                       "output": "Output", "zone": "Zone", "input": "Zone"}.get(feedback.lower())
                source = next((e for e in root.iter(tag) if e.get("Name") == feedback_name), None) if tag else None
                if feedback_name and tag and source is None:
                    diagnostics.append(f"Home Control {g}/{k}: unresolved {feedback} feedback {feedback_name}")
                if label or actions or feedback.lower() not in ("", "none"):
                    controls[g, k] = Control(g, k, phrase(group), label or f"Control {k}",
                                             feedback, feedback_name, tuple(actions),
                                             int(source.get("Number")) if source is not None else None)
            except ValueError as exc:
                diagnostics.append(f"Home Control {group.get('Number')}/{item.get('Number')}: {exc}")
    return controls, diagnostics
