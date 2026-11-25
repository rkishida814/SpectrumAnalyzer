// 計算用の Web Worker。Pyodide（ブラウザ内の Python）で core/ と state.py をそのまま動かす。
// 計算はページを開いた PC の中で行われ、データはどこにも送られない。
importScripts("https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.js");

self.reportProgress = (step, max) => self.postMessage({ type: "progress", step, max });

let bridge = null;

const ready = (async () => {
  const pyodide = await loadPyodide();
  await pyodide.loadPackage(["numpy", "scipy"]);

  // デスクトップ版と同じソースを読み込む（web/ の一つ上の階層）
  const files = ["core/parser.py", "core/math_utils.py", "core/fitter.py", "state.py"];
  pyodide.FS.mkdirTree("/app/core");
  pyodide.FS.writeFile("/app/core/__init__.py", "");
  for (const f of files) {
    // no-cache: 更新した .py をブラウザのキャッシュで古いまま使わない（変わっていなければ 304 で軽い）
    const r = await fetch(new URL("../" + f, self.location), { cache: "no-cache" });
    if (!r.ok) throw new Error(`failed to load ${f} (${r.status})`);
    pyodide.FS.writeFile("/app/" + f, await r.text());
  }
  const b = await fetch(new URL("bridge.py", self.location), { cache: "no-cache" });
  if (!b.ok) throw new Error(`failed to load bridge.py (${b.status})`);
  pyodide.FS.writeFile("/app/bridge.py", await b.text());

  pyodide.runPython("import sys; sys.path.insert(0, '/app')");
  bridge = pyodide.pyimport("bridge");
  self.pyodide = pyodide;
})();

ready.then(
  () => self.postMessage({ type: "ready" }),
  (e) => self.postMessage({ type: "init_error", error: String(e) })
);

self.onmessage = async (ev) => {
  const { id, cmd, args } = ev.data;
  try {
    await ready;
    let out;
    if (cmd === "parse") {
      const path = "/tmp/upload.dat";
      self.pyodide.FS.writeFile(path, new Uint8Array(args.bytes));
      out = bridge.parse(path);
    } else if (["smooth", "integral", "fit", "peaks_op"].includes(cmd)) {
      out = bridge[cmd](JSON.stringify(args));
    } else {
      throw new Error("unknown command: " + cmd);
    }
    self.postMessage({ type: "result", id, ok: true, result: JSON.parse(out) });
  } catch (e) {
    self.postMessage({ type: "result", id, ok: false, error: String(e) });
  }
};
