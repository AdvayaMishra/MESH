// TEST-ONLY minimal zustand stand-in, used by scripts/run-verify.sh when the real package isn't installed.
// Implements just what MESH stores use: create (plain + curried), getState/setState, persist/createJSONStorage no-ops.
function make(init) {
  let state; const set = (p) => { const n = typeof p === "function" ? p(state) : p; state = { ...state, ...n }; };
  const get = () => state; state = init(set, get, {});
  const hook = (sel) => (sel ? sel(state) : state); hook.getState = get; hook.setState = set; hook.persist = { rehydrate: () => Promise.resolve() };
  return hook;
}
exports.create = (init) => (init ? make(init) : (i) => make(i));
exports.persist = (init) => init; exports.createJSONStorage = () => undefined;
