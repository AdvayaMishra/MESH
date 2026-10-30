// TEST-ONLY stub: the verify scripts import data/store modules that reference React hooks but never call them.
module.exports = { useMemo: (f) => f(), useState: (v) => [v, () => {}], useEffect() {}, useRef: (v) => ({ current: v }), createElement() {} };
