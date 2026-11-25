(function () {
  "use strict";

  const PYODIDE_INDEX_URL = "https://cdn.jsdelivr.net/npm/pyodide@0.26.4/";
  const LOAD_TIMEOUT_MS = 45000;
  const EXEC_TIMEOUT_MS = 10000;

  const WORKER_SOURCE = `
    let pyodide = null;
    let loadingPromise = null;

    async function ensurePyodide() {
      if (pyodide) return pyodide;
      if (!loadingPromise) {
        loadingPromise = (async () => {
          importScripts("${PYODIDE_INDEX_URL}pyodide.js");
          pyodide = await loadPyodide({ indexURL: "${PYODIDE_INDEX_URL}" });
          self.postMessage({ type: "ready" });
          return pyodide;
        })();
      }
      return loadingPromise;
    }

    self.onmessage = async (event) => {
      const { id, code } = event.data;
      try {
        const py = await ensurePyodide();
        self.postMessage({ type: "running", id });
        py.globals.set("_user_code", code);
        const result = await py.runPythonAsync(\`
import io, traceback, contextlib
_buf_out = io.StringIO()
_buf_err = io.StringIO()
_ok = True
try:
    with contextlib.redirect_stdout(_buf_out), contextlib.redirect_stderr(_buf_err):
        exec(_user_code, {"__name__": "__main__"})
except Exception:
    _ok = False
    traceback.print_exc(file=_buf_err)
(_ok, _buf_out.getvalue(), _buf_err.getvalue())
\`);
        py.globals.delete("_user_code");
        const [ok, stdout, stderr] = result.toJs();
        result.destroy();
        self.postMessage({ type: "result", id, ok, stdout, stderr });
      } catch (err) {
        self.postMessage({
          type: "result",
          id,
          ok: false,
          stdout: "",
          stderr: String(err && err.message ? err.message : err)
        });
      }
    };
  `;

  let worker = null;
  let workerReady = false;
  let jobCounter = 0;
  let activeJob = null;

  function resetWorker() {
    if (worker) {
      try {
        worker.terminate();
      } catch (_) {}
    }
    worker = null;
    workerReady = false;
  }

  function getWorker() {
    if (worker) return worker;
    const blob = new Blob([WORKER_SOURCE], { type: "application/javascript" });
    const url = URL.createObjectURL(blob);
    worker = new Worker(url);
    URL.revokeObjectURL(url);

    worker.onmessage = (event) => {
      const msg = event.data;
      if (msg.type === "ready") {
        workerReady = true;
        if (activeJob && activeJob.onReady) activeJob.onReady();
        return;
      }
      if (msg.type === "running") {
        if (activeJob && activeJob.id === msg.id && activeJob.onRunning) {
          activeJob.onRunning();
        }
        return;
      }
      if (msg.type === "result") {
        if (activeJob && activeJob.id === msg.id) {
          const job = activeJob;
          activeJob = null;
          clearTimeout(job.timer);
          job.resolve(msg);
        }
      }
    };

    worker.onerror = (err) => {
      if (activeJob) {
        const job = activeJob;
        activeJob = null;
        clearTimeout(job.timer);
        job.reject(new Error(err.message || "Python 実行環境の読み込みに失敗しました。"));
      }
      resetWorker();
    };

    return worker;
  }

  function runPythonInWorker(code, onStatus) {
    if (activeJob) {
      return Promise.reject(new Error("他のコードが実行中です。少し待ってから再度お試しください。"));
    }

    return new Promise((resolve, reject) => {
      const id = ++jobCounter;
      const w = getWorker();

      const setJobTimeout = (ms, message) => {
        if (activeJob && activeJob.timer) clearTimeout(activeJob.timer);
        if (!activeJob) return;
        activeJob.timer = setTimeout(() => {
          const job = activeJob;
          activeJob = null;
          resetWorker();
          if (job) job.reject(new Error(message));
        }, ms);
      };

      activeJob = {
        id,
        resolve,
        reject,
        timer: null,
        onReady: () => {
          if (onStatus) onStatus("実行中...");
        },
        onRunning: () => {
          if (onStatus) onStatus("実行中...");
          setJobTimeout(
            EXEC_TIMEOUT_MS,
            "実行がタイムアウトしました（10秒超過）。無限ループになっていないか確認してください。"
          );
        }
      };

      if (workerReady) {
        if (onStatus) onStatus("実行中...");
        setJobTimeout(
          EXEC_TIMEOUT_MS,
          "実行がタイムアウトしました（10秒超過）。無限ループになっていないか確認してください。"
        );
      } else {
        if (onStatus) onStatus("Python を起動中...（初回のみ数秒）");
        setJobTimeout(
          LOAD_TIMEOUT_MS,
          "Python 実行環境（Pyodide）の読み込みがタイムアウトしました。ネットワーク接続を確認して再度お試しください。"
        );
      }

      w.postMessage({ id, code });
    });
  }

  function enhancePythonBlock(highlightDiv) {
    if (highlightDiv.dataset.pyRunnerInit === "1") return;
    const codeEl = highlightDiv.querySelector("pre > code");
    if (!codeEl) return;

    highlightDiv.dataset.pyRunnerInit = "1";
    const originalCode = codeEl.textContent.replace(/\n$/, "");
    let currentCode = originalCode;
    let isEditing = false;

    const panel = document.createElement("div");
    panel.className = "py-runner";

    const bar = document.createElement("div");
    bar.className = "py-runner-bar";

    const runBtn = document.createElement("button");
    runBtn.type = "button";
    runBtn.className = "py-runner-btn py-runner-btn-run";
    runBtn.textContent = "▶ 実行";

    const editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.className = "py-runner-btn py-runner-btn-edit";
    editBtn.textContent = "編集";

    const resetBtn = document.createElement("button");
    resetBtn.type = "button";
    resetBtn.className = "py-runner-btn py-runner-btn-reset";
    resetBtn.textContent = "リセット";
    resetBtn.hidden = true;

    const note = document.createElement("span");
    note.className = "py-runner-note";
    note.textContent = "ブラウザ内で実行（Pyodide）";

    bar.append(runBtn, editBtn, resetBtn, note);

    const editor = document.createElement("textarea");
    editor.className = "py-runner-editor";
    editor.spellcheck = false;
    editor.value = originalCode;
    editor.hidden = true;

    const output = document.createElement("pre");
    output.className = "py-runner-output";
    output.hidden = true;

    panel.append(editor, bar, output);
    highlightDiv.insertAdjacentElement("afterend", panel);

    function syncEditorHeight() {
      const lines = editor.value.split("\n").length;
      editor.rows = Math.min(Math.max(lines + 1, 5), 32);
    }

    editor.addEventListener("input", () => {
      currentCode = editor.value;
      resetBtn.hidden = currentCode === originalCode;
      syncEditorHeight();
    });

    editor.addEventListener("keydown", (e) => {
      if (e.key === "Tab") {
        e.preventDefault();
        const start = editor.selectionStart;
        const end = editor.selectionEnd;
        editor.value =
          editor.value.slice(0, start) + "    " + editor.value.slice(end);
        editor.selectionStart = editor.selectionEnd = start + 4;
        currentCode = editor.value;
        resetBtn.hidden = currentCode === originalCode;
      } else if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        runBtn.click();
      }
    });

    editBtn.addEventListener("click", () => {
      isEditing = !isEditing;
      if (isEditing) {
        editor.value = currentCode;
        syncEditorHeight();
        highlightDiv.hidden = true;
        editor.hidden = false;
        editBtn.textContent = "表示に戻す";
        editor.focus();
      } else {
        highlightDiv.hidden = false;
        editor.hidden = true;
        editBtn.textContent = "編集";
      }
    });

    resetBtn.addEventListener("click", () => {
      currentCode = originalCode;
      editor.value = originalCode;
      resetBtn.hidden = true;
      syncEditorHeight();
    });

    runBtn.addEventListener("click", async () => {
      runBtn.disabled = true;
      output.hidden = false;
      output.classList.remove("is-error");
      output.textContent = workerReady
        ? "実行中..."
        : "Python を起動中...（初回のみ数秒）";

      try {
        const res = await runPythonInWorker(currentCode, (status) => {
          output.textContent = status;
        });
        if (res.ok) {
          const text = (res.stdout || "") + (res.stderr ? "\n" + res.stderr : "");
          output.textContent = text.trim() ? text.replace(/\n$/, "") : "（出力なし）";
        } else {
          output.classList.add("is-error");
          const text = (res.stdout ? res.stdout + "\n" : "") + (res.stderr || "エラーが発生しました。");
          output.textContent = text.replace(/\n$/, "");
        }
      } catch (err) {
        output.classList.add("is-error");
        output.textContent = String(err && err.message ? err.message : err);
      } finally {
        runBtn.disabled = false;
      }
    });
  }

  function initPyRunners() {
    document
      .querySelectorAll(".md-typeset .language-python.highlight")
      .forEach(enhancePythonBlock);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initPyRunners);
  } else {
    initPyRunners();
  }

  if (typeof document$ !== "undefined") {
    document$.subscribe(initPyRunners);
  }
})();
