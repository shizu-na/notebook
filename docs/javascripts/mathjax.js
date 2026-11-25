function markOverflowingInlineMath() {
  const spans = document.querySelectorAll(".md-typeset span.arithmatex");
  spans.forEach((span) => {
    span.classList.remove("math-overflow");
    const container =
      span.closest("p, li, blockquote, td, th, dd, figcaption") ||
      span.parentElement;
    if (!container) return;
    const available = container.clientWidth;
    const mjx = span.querySelector("mjx-container");
    const width = mjx
      ? mjx.getBoundingClientRect().width
      : span.getBoundingClientRect().width;
    if (available > 0 && width > available - 4) {
      span.classList.add("math-overflow");
    }
  });
}

window.MathJax = {
  tex: {
    inlineMath: [["\\(", "\\)"]],
    displayMath: [["\\[", "\\]"]],
    processEscapes: true,
    processEnvironments: true,
    macros: {
      boldsymbol: ["\\mathbf{#1}", 1],
      bm: ["\\mathbf{#1}", 1]
    }
  },
  options: {
    ignoreHtmlClass: ".*|",
    processHtmlClass: "arithmatex"
  },
  startup: {
    pageReady: () => {
      return MathJax.startup.defaultPageReady().then(() => {
        markOverflowingInlineMath();
      });
    }
  }
};

// Material のページ遷移（instant loading）後にも数式を再描画し、幅広インライン数式を再判定する
if (typeof document$ !== "undefined") {
  document$.subscribe(() => {
    MathJax.startup.output.clearCache();
    MathJax.typesetClear();
    MathJax.texReset();
    MathJax.typesetPromise().then(() => {
      markOverflowingInlineMath();
    });
  });
}

let mathResizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(mathResizeTimer);
  mathResizeTimer = setTimeout(markOverflowingInlineMath, 150);
});
