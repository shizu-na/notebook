/* 左右サイドバー（ナビゲーション・目次）の個別開閉トグル（PC表示向け） */
(function () {
  var NAV_KEY = "notebook_hide_nav_sidebar";
  var TOC_KEY = "notebook_hide_toc_sidebar";
  var root = document.documentElement;

  function loadFlag(key) {
    try {
      return localStorage.getItem(key) === "1";
    } catch (_) {
      return false;
    }
  }

  function saveFlag(key, value) {
    try {
      localStorage.setItem(key, value ? "1" : "0");
    } catch (_) {
      /* プライベートブラウジング等で保存不可でも動作を継続 */
    }
  }

  // 初期描画のちらつきを抑えるため、DOM構築前にクラスを反映
  if (loadFlag(NAV_KEY)) root.classList.add("hide-nav-sidebar");
  if (loadFlag(TOC_KEY)) root.classList.add("hide-toc-sidebar");

  function createIconSvg(side) {
    // side === "left": 左パネルアイコン, side === "right": 右パネルアイコン
    var dividerX = side === "left" ? "9" : "15";
    var fillRect =
      side === "left"
        ? '<rect x="3" y="4" width="6" height="16" rx="1" fill="currentColor" opacity="0.28"/>'
        : '<rect x="15" y="4" width="6" height="16" rx="1" fill="currentColor" opacity="0.28"/>';
    return (
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true">' +
      fillRect +
      '<rect x="3" y="4" width="18" height="16" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/>' +
      '<line x1="' +
      dividerX +
      '" y1="4" x2="' +
      dividerX +
      '" y2="20" stroke="currentColor" stroke-width="1.8"/>' +
      "</svg>"
    );
  }

  function updateButtonState(btn, hidden, labelOpen, labelClose) {
    btn.setAttribute("aria-pressed", hidden ? "true" : "false");
    var tip = hidden ? labelOpen : labelClose;
    btn.setAttribute("title", tip);
    btn.setAttribute("aria-label", tip);
    btn.classList.toggle("is-collapsed", hidden);
  }

  function mountButtons() {
    var headerInner = document.querySelector(".md-header__inner");
    if (!headerInner || headerInner.querySelector(".sidebar-toggle-group")) return;

    var hasNav = !!document.querySelector(".md-sidebar--primary");
    var hasToc = !!document.querySelector(".md-sidebar--secondary");
    if (!hasNav && !hasToc) return;

    var group = document.createElement("div");
    group.className = "sidebar-toggle-group";

    if (hasNav) {
      var navBtn = document.createElement("button");
      navBtn.type = "button";
      navBtn.className = "md-header__button md-icon sidebar-toggle-btn sidebar-toggle-nav";
      navBtn.innerHTML = createIconSvg("left");
      updateButtonState(
        navBtn,
        root.classList.contains("hide-nav-sidebar"),
        "左サイドバー（ナビ）を開く",
        "左サイドバー（ナビ）を閉じる"
      );
      navBtn.addEventListener("click", function () {
        var hidden = root.classList.toggle("hide-nav-sidebar");
        saveFlag(NAV_KEY, hidden);
        updateButtonState(
          navBtn,
          hidden,
          "左サイドバー（ナビ）を開く",
          "左サイドバー（ナビ）を閉じる"
        );
      });
      group.appendChild(navBtn);
    }

    if (hasToc) {
      var tocBtn = document.createElement("button");
      tocBtn.type = "button";
      tocBtn.className = "md-header__button md-icon sidebar-toggle-btn sidebar-toggle-toc";
      tocBtn.innerHTML = createIconSvg("right");
      updateButtonState(
        tocBtn,
        root.classList.contains("hide-toc-sidebar"),
        "右サイドバー（目次）を開く",
        "右サイドバー（目次）を閉じる"
      );
      tocBtn.addEventListener("click", function () {
        var hidden = root.classList.toggle("hide-toc-sidebar");
        saveFlag(TOC_KEY, hidden);
        updateButtonState(
          tocBtn,
          hidden,
          "右サイドバー（目次）を開く",
          "右サイドバー（目次）を閉じる"
        );
      });
      group.appendChild(tocBtn);
    }

    // パレット切替または検索ボックスの手前に挿入
    var anchor =
      headerInner.querySelector("form.md-header__option") ||
      headerInner.querySelector(".md-search") ||
      headerInner.querySelector(".md-header__source");
    if (anchor) {
      headerInner.insertBefore(group, anchor);
    } else {
      headerInner.appendChild(group);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountButtons);
  } else {
    mountButtons();
  }
})();
