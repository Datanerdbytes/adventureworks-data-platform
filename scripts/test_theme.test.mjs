import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const script = readFileSync("my-dash-app/templates/theme-script.html", "utf8")
  .replace("<script>", "")
  .replace("</script>", "");
function environment(saved, systemDark = false, blocked = false) {
  const events = {};
  const classes = new Set();
  const media = {
    matches: systemDark,
    addEventListener: (_, fn) => {
      media.change = fn;
    },
  };
  const body = {
    classList: {
      toggle: (key, enabled) =>
        enabled ? classes.add(key) : classes.delete(key),
    },
  };
  const root = { classList: body.classList };
  const window = {
    matchMedia: () => media,
    localStorage: {
      getItem: () => {
        if (blocked) throw Error("disabled");
        return saved;
      },
    },
    addEventListener: (name, fn) => {
      events[name] = fn;
    },
    dispatchEvent: () => {},
  };
  vm.runInNewContext(script, {
    window,
    document: {
      body,
      documentElement: root,
      querySelector: () => null,
      addEventListener: (name, fn) => {
        events[name] = fn;
      },
    },
    Event: class {},
  });
  return {
    window,
    classes,
    media,
    events,
    save: (value) => {
      saved = value;
    },
  };
}

test("first paint stays light until System or Dark is explicitly selected", () => {
  const env = environment(null, true);
  assert.ok(env.classes.has("theme-light"));
  env.window.awTheme.apply({ theme: "system" });
  assert.ok(env.classes.has("theme-dark"));
  env.media.matches = false;
  env.media.change();
  assert.ok(env.classes.has("theme-light"));
  env.window.awTheme.apply({ theme: "dark" });
  env.media.change();
  assert.ok(env.classes.has("theme-dark"));
});
test("saved preference survives load; storage events sync tabs and reset", () => {
  const env = environment('{"theme":"dark","fontSize":"large"}');
  assert.ok(env.classes.has("theme-dark"));
  assert.ok(env.classes.has("font-size-large"));
  env.save('{"theme":"light"}');
  env.events.storage({ key: "display-preferences" });
  assert.ok(env.classes.has("theme-light"));
  assert.ok(!env.classes.has("font-size-large"));
  env.media.matches = true;
  env.save(null);
  env.events.storage({ key: null });
  assert.ok(env.classes.has("theme-light"));
});
test("invalid or unavailable storage safely defaults to light", () => {
  for (const env of [
    environment("invalid", true),
    environment(null, true, true),
  ]) {
    assert.ok(env.classes.has("theme-light"));
  }
});

test("charts theme annotations and replaced figures without a render loop", async () => {
  const source = readFileSync("my-dash-app/assets/theme-charts.js", "utf8");
  const tokens = {
    surface: "#121a2e",
    text: "#f1f5f9",
    muted: "#94a3b8",
    border: "#334155",
    "surface-overlay": "#22304a",
  };
  const frames = [];
  const graph = {
    layout: {
      xaxis: {},
      yaxis2: {},
      annotations: [
        { text: "Total sales · USD", font: { color: "#243B45", size: 22 } },
        { text: "Comparison baseline", x: 0.5 },
      ],
    },
    _fullLayout: {},
    on: (_, fn) => {
      graph.afterplot = fn;
    },
  };
  let calls = 0;
  vm.runInNewContext(source, {
    window: {
      addEventListener: () => {},
      Plotly: {
        relayout: (gd, update) => {
          calls++;
          for (const [key, value] of Object.entries(update)) {
            const path = key.replace(/\[(\d+)\]/g, ".$1").split(".");
            let target = gd.layout;
            for (const part of path.slice(0, -1)) target = target[part] ||= {};
            target[path.at(-1)] = value;
          }
          gd.afterplot();
          return Promise.resolve();
        },
      },
    },
    document: { documentElement: {}, querySelectorAll: () => [graph] },
    getComputedStyle: () => ({
      getPropertyValue: (name) => tokens[name.slice(2)],
    }),
    requestAnimationFrame: (fn) => frames.push(fn),
    MutationObserver: class {
      observe() {}
    },
  });
  frames.shift()();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(graph.layout.paper_bgcolor, tokens.surface);
  assert.equal(graph.layout.yaxis2.color, tokens.muted);
  assert.equal(graph.layout.annotations[0].font.color, tokens.text);
  assert.equal(graph.layout.annotations[0].font.size, 22);
  assert.equal(graph.layout.annotations[0].text, "Total sales · USD");
  assert.equal(graph.layout.annotations[1].font.color, tokens.text);
  assert.equal(graph.layout.annotations[1].x, 0.5);
  frames.shift()();
  assert.equal(calls, 1);
  graph.layout = {
    xaxis: {},
    yaxis2: {},
    annotations: [{ text: "Filtered total", font: { color: "#243B45" } }],
  };
  graph.afterplot();
  frames.shift()();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(calls, 2);
  assert.equal(graph.layout.annotations[0].font.color, tokens.text);
  tokens.surface = "#FFFFFF";
  tokens.text = "#243B45";
  graph.afterplot();
  frames.shift()();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(graph.layout.paper_bgcolor, "#FFFFFF");
  assert.equal(graph.layout.annotations[0].font.color, tokens.text);
  frames.shift()();
  assert.equal(calls, 3);
});

test("settings waits for hydration and returns the single preferences output", () => {
  const source = readFileSync("my-dash-app/pages/settings.py", "utf8");
  const start = source.indexOf("function(theme, density");
  const end = source.indexOf('"""', start);
  const callback = vm.runInNewContext(
    "(" + source.slice(start, end).trim() + ")",
    {
      window: { dash_clientside: { no_update: "no-update" } },
    },
  );
  assert.equal(callback(null), "no-update");
  const result = callback(
    "dark",
    "compact",
    "on",
    "large",
    "line",
    "compact",
    "USD",
    true,
    "brief",
    "CSV",
    false,
    20,
    { customPreference: true },
  );
  assert.equal(result.theme, "dark");
  assert.equal(result.pageSize, 20);
  assert.equal(result.customPreference, true);
  assert.equal(Array.isArray(result), false);
});

test("opening Settings preserves explicit Light even on a dark system", () => {
  const env = environment('{"theme":"light"}', true);
  env.events.DOMContentLoaded();
  env.media.change();
  assert.ok(env.classes.has("theme-light"));
});

test("settings hydration never writes a default or overwrites a saved preference", () => {
  const source = readFileSync("my-dash-app/pages/settings.py", "utf8");
  const start = source.indexOf("function(theme, density");
  const end = source.indexOf('"""', start);
  const callback = vm.runInNewContext(
    "(" + source.slice(start, end).trim() + ")",
    {
      window: { dash_clientside: { no_update: "no-update" } },
    },
  );
  const defaults = [
    "light",
    "comfortable",
    "off",
    "default",
    "line",
    "compact",
    "USD",
    true,
    "brief",
    "CSV",
    false,
    10,
  ];
  assert.equal(callback(...defaults, { pageSize: 10 }), "no-update");
  assert.equal(
    callback(...defaults, { theme: "light", pageSize: 10 }),
    "no-update",
  );
  const system = [...defaults];
  system[0] = "system";
  assert.equal(
    callback(...system, { theme: "system", pageSize: 10 }),
    "no-update",
  );
  assert.equal(
    callback(...system, { theme: "light", pageSize: 10 }).theme,
    "system",
  );
  assert.equal(
    callback(...defaults, { theme: "dark", pageSize: 10 }).theme,
    "light",
  );
});

test("toggle switches preserve the existing on/off storage contract", () => {
  const source = readFileSync("my-dash-app/pages/settings.py", "utf8");
  const start = source.indexOf("function(theme, density");
  const end = source.indexOf('"""', start);
  const callback = vm.runInNewContext(
    "(" + source.slice(start, end).trim() + ")",
    {
      window: { dash_clientside: { no_update: "no-update" } },
    },
  );
  const values = [
    "light",
    "comfortable",
    "off",
    "default",
    "line",
    "compact",
    "USD",
    false,
    "brief",
    "CSV",
    true,
    10,
  ];
  const result = callback(...values, {
    theme: "light",
    pipelineAlerts: "on",
    includeFilters: "off",
  });
  assert.equal(result.pipelineAlerts, "off");
  assert.equal(result.includeFilters, "on");
  assert.equal(callback(...values, result), "no-update");
});
