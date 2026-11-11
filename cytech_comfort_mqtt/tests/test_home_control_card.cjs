// A small DOM harness checks state transitions without a running HA instance.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.attributes = {}; this.textContent = ''; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(key, value) { this.attributes[key] = value; }
  attachShadow() { this.shadowRoot = new Element('shadow'); }
}
let Card;
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../home_assistant/www/comfort-home-control-card.js'), 'utf8'), {
  HTMLElement: Element, document: { createElement: tag => new Element(tag) },
  customElements: { get: () => undefined, define: (_, value) => { Card = value; } }
});
const all = node => [node, ...node.children.flatMap(all)];
const texts = card => all(card.shadowRoot).map(n => n.textContent).join('|');
const item = (group = 0, label = 'Lamp') => ({group, key: 2, group_label: `Room ${group}`, label,
  feedback_type: 'Counter', actions: [{ number: 1, label: 'On' }]});
function setup(items = [item()]) {
  const card = new Card(); card.setConfig({domain: 'custom'});
  const states = {
    'sensor.renamed_menu': { entity_id: 'sensor.renamed_menu', state: '1', attributes:
      { comfort_home_control_menu: 'custom', items } },
    'sensor.renamed': { entity_id: 'sensor.renamed', state: '255', attributes:
      { comfort_home_control: 'custom:0:2:state' } },
    'button.renamed': { entity_id: 'button.renamed', state: 'unknown', attributes:
      { comfort_home_control: 'custom:0:2:1' } }
  };
  const calls = [];
  const hass = {states, callService: async (...args) => { calls.push(args); }};
  card.hass = hass;
  return { card, states, hass, calls };
}

test('renders feedback and invokes renamed action entity through HA', async () => {
  const {card, calls} = setup();
  assert.match(texts(card), /Feedback: 255/);
  const button = all(card.shadowRoot).find(n => n.tag === 'button' && n.textContent === 'On');
  assert.equal(button.disabled, false);
  await button.onclick();
  assert.equal(JSON.stringify(calls), JSON.stringify([['button', 'press', {entity_id: 'button.renamed'}]]));
});

test('changed metadata replaces groups, labels and actions with unchanged config', () => {
  const {card, states, hass} = setup();
  states['sensor.renamed_menu'].attributes.items = [item(4, '<script>New control</script>')];
  card.hass = hass;
  assert.match(texts(card), /Room 4/);
  assert.match(texts(card), /<script>New control<\/script>/);
  assert.doesNotMatch(texts(card), /Room 0/);
  assert.equal(card.selected, 4);
  assert.equal(all(card.shadowRoot).find(n => n.textContent === 'On').disabled, true);
});

test('offline menu disables actions, empty menu and missing metadata are explicit', () => {
  const {card, states, hass} = setup();
  states['sensor.renamed_menu'].state = 'unavailable'; card.hass = hass;
  assert.match(texts(card), /Feedback: Unavailable/);
  assert.equal(all(card.shadowRoot).find(n => n.textContent === 'On').disabled, true);
  states['sensor.renamed_menu'].attributes.items = []; card.hass = hass;
  assert.match(texts(card), /No Home Control definitions/);
  delete states['sensor.renamed_menu']; card.hass = hass;
  assert.match(texts(card), /Waiting for Home Control discovery/);
});

test('service failure is displayed without claiming successful control', async () => {
  const {card, hass} = setup();
  hass.callService = async () => { throw new Error('Denied'); };
  await all(card.shadowRoot).find(n => n.textContent === 'On').onclick();
  assert.match(texts(card), /Action could not be sent: Denied/);
  assert.match(texts(card), /Feedback: 255/);
});
