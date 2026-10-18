/* Apply semantic CSS tokens after every Plotly render, including filtered figures. */
(function () {
  const bound = new WeakSet();
  const busy = new WeakSet();
  let scheduled = false;
  function styleGraph(graph) {
    if (!window.Plotly || !graph._fullLayout || busy.has(graph)) return;
    if (!bound.has(graph) && typeof graph.on === "function") {
      bound.add(graph);
      graph.on("plotly_afterplot", schedule);
    }
    const css = getComputedStyle(document.documentElement);
    const token = (name) => css.getPropertyValue("--" + name).trim();
    const update = {
      paper_bgcolor: token("surface"),
      plot_bgcolor: token("surface"),
      "font.color": token("muted"),
      "title.font.color": token("text"),
      "legend.font.color": token("text"),
      "legend.bgcolor": token("surface"),
      "hoverlabel.bgcolor": token("surface-overlay"),
      "hoverlabel.font.color": token("text"),
    };
    // Cover secondary axes without changing ranges, trace colors, or chart choices.
    Object.keys(graph.layout).forEach((key) => {
      if (/^[xy]axis\d*$/.test(key)) {
        update[key + ".color"] = token("muted");
        update[key + ".gridcolor"] = token("border");
        update[key + ".zerolinecolor"] = token("border");
      }
      if (/^geo\d*$/.test(key)) update[key + ".bgcolor"] = token("surface");
    });
    // Explicit annotation fonts do not inherit layout.font (e.g. donut totals).
    (graph.layout.annotations || []).forEach((_, index) => {
      update[`annotations[${index}].font.color`] = token("text");
    });
    const valueAt = (object, path) =>
      path
        .replace(/\[(\d+)\]/g, ".$1")
        .split(".")
        .reduce((value, key) => value && value[key], object);
    if (
      Object.entries(update).every(
        ([key, value]) => valueAt(graph.layout, key) === value,
      )
    )
      return;
    busy.add(graph);
    Promise.resolve(window.Plotly.relayout(graph, update)).finally(() => {
      busy.delete(graph);
    });
  }
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      document.querySelectorAll(".js-plotly-plot").forEach(styleGraph);
    });
  }
  window.addEventListener("aw-theme-change", schedule);
  new MutationObserver(schedule).observe(document.documentElement, {
    childList: true,
    subtree: true,
  });
  schedule();
})();
