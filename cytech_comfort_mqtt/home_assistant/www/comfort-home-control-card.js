/* Dynamic Comfort menu. Uses HA state and button.press; no broker credentials. */
class ComfortHomeControlCard extends HTMLElement {
  setConfig(config) {
    this.config = { domain: "cytech_comfort_mqtt", ...config };
    this.attachShadowIfNeeded();
    this.signature = undefined;
    if (this._hass) this.render();
  }

  attachShadowIfNeeded() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
  }

  set hass(hass) { this._hass = hass; if (this.config) this.render(); }
  getCardSize() { return 8; }

  render() {
    const states = Object.values(this._hass.states);
    const domain = this.config.domain;
    const menu = states.find(s => s.attributes.comfort_home_control_menu === domain);
    const relevant = states.filter(s => s.attributes.comfort_home_control?.startsWith(`${domain}:`));
    const signature = JSON.stringify([menu, relevant, this.selected]);
    if (signature === this.signature) return;
    this.signature = signature;
    const root = this.shadowRoot;
    root.replaceChildren();
    const style = document.createElement("style");
    style.textContent = `
      ha-card { padding: 20px; } h2 { margin: 0 0 12px; }
      p { color: var(--secondary-text-color); } nav { display:flex; gap:8px; flex-wrap:wrap; margin:16px 0; }
      button { font:inherit; cursor:pointer; border:1px solid var(--divider-color); border-radius:12px;
        padding:10px 16px; color:var(--primary-text-color); background:var(--card-background-color); }
      button[aria-pressed="true"] { background:var(--primary-color); color:var(--text-primary-color); }
      button:disabled { opacity:.5; cursor:default; } button:focus-visible { outline:3px solid var(--primary-color); }
      .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr)); gap:12px; }
      section { padding:16px; border:1px solid var(--divider-color); border-radius:12px; }
      h3 { margin:0 0 12px; } .actions { display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }
      .status { font-size:1.1em; } .error { color:var(--error-color); }
    `;
    root.append(style);
    const card = document.createElement("ha-card");
    root.append(card);
    const text = (parent, tag, value, className) => {
      const node = document.createElement(tag);
      node.textContent = value;
      if (className) node.className = className;
      parent.append(node);
      return node;
    };
    text(card, "h2", this.config.title || "Comfort Home Control");
    if (!menu) { text(card, "p", "Waiting for Home Control discovery and menu metadata."); return; }
    const offline = menu.state === "unavailable" || menu.state === "unknown";
    text(card, "p", offline ? "Comfort is unavailable. Actions are disabled." :
      "Feedback comes from Comfort. Actions do not predict device state.");
    if (this.error) text(card, "p", this.error, "error").setAttribute("role", "alert");
    const items = Array.isArray(menu.attributes.items) ? menu.attributes.items : [];
    if (!items.length) { text(card, "p", "No Home Control definitions in the active CCLX."); return; }
    const groups = [...new Set(items.map(c => c.group))].sort((a, b) => a - b);
    if (!groups.includes(this.selected)) this.selected = groups[0];
    const nav = document.createElement("nav");
    nav.setAttribute("aria-label", "Home Control groups"); card.append(nav);
    for (const group of groups) {
      const item = items.find(c => c.group === group);
      const button = text(nav, "button", item.group_label || `Group ${group}`);
      button.setAttribute("aria-pressed", String(group === this.selected));
      button.onclick = () => { this.selected = group; this.render(); };
    }
    const grid = document.createElement("div"); grid.className = "grid"; card.append(grid);
    const resolve = (c, suffix) => relevant.find(s =>
      s.attributes.comfort_home_control === `${domain}:${c.group}:${c.key}:${suffix}`);
    for (const c of items.filter(c => c.group === this.selected).sort((a, b) => a.key - b.key)) {
      const section = document.createElement("section"); grid.append(section);
      text(section, "h3", c.label);
      const hasFeedback = !["", "none", "x10"].includes((c.feedback_type || "").toLowerCase());
      if (hasFeedback) {
        const state = resolve(c, "state");
        const value = offline ? "Unavailable" : !state ? "Waiting for entity" :
          state.state === "unknown" ? "Unknown" : state.state === "unavailable" ? "Unavailable" : state.state;
        text(section, "div", `Feedback: ${value}`, "status");
      } else text(section, "div", "No status feedback");
      const actions = document.createElement("div"); actions.className = "actions"; section.append(actions);
      for (const a of c.actions || []) {
        const entity = resolve(c, a.number);
        const button = text(actions, "button", a.label || `Action ${a.number}`);
        button.disabled = offline || !entity || entity.state === "unavailable" || this.busy === entity.entity_id;
        button.onclick = async () => {
          this.busy = entity.entity_id; this.error = ""; this.signature = undefined; this.render();
          try { await this._hass.callService("button", "press", { entity_id: entity.entity_id }); }
          catch (error) { this.error = `Action could not be sent: ${error.message || error}`; }
          finally { this.busy = undefined; this.signature = undefined; this.render(); }
        };
      }
      if (!(c.actions || []).length) text(section, "p", "No configured actions");
    }
  }
}
if (!customElements.get("comfort-home-control-card")) {
  customElements.define("comfort-home-control-card", ComfortHomeControlCard);
}
