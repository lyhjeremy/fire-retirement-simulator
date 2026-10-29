/* Runs the engine off the main thread. Messages: {id, kind: "run" | "solve", p, target}. */
importScripts("data/returns.js", "engine.js");
self.onmessage = function (e) {
  var m = e.data;
  self.postMessage(handle(m));
};
function handle(m) {
  var D = self.RETURNS;
  if (m.kind === "run") {
    var r = FireEngine.run(m.p, D, true);
    var h = m.p.mode === "historical" ? r : FireEngine.run(Object.assign({}, m.p, { mode: "historical" }), D, true);
    return { id: m.id, kind: "run", r: r, h: h };
  }
  return { id: m.id, kind: "solve", s: FireEngine.solve(m.p, D, m.target, m.p.sims) };
}
self.handle = handle;
