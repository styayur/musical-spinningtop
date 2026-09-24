/* Spinning Top - 每日音乐剧 前端逻辑 */
(function () {
  "use strict";

  var state = { offset: 0 };

  var el = {
    card: document.getElementById("card"),
    hero: document.getElementById("hero"),
    title: document.getElementById("title"),
    composer: document.getElementById("composer"),
    yearChip: document.getElementById("yearChip"),
    datePill: document.getElementById("datePill"),
    frontBody: document.getElementById("frontBody"),
    scrollHint: document.getElementById("scrollHint"),
    gallery: document.getElementById("gallery"),
    intro: document.getElementById("intro"),
    translatorTag: document.getElementById("translatorTag"),
    backTitle: document.getElementById("backTitle"),
    officialBtn: document.getElementById("officialBtn"),
    feverBtn: document.getElementById("feverBtn"),
    wikiBtn: document.getElementById("wikiBtn"),
    prevBtn: document.getElementById("prevBtn"),
    nextBtn: document.getElementById("nextBtn"),
    todayBtn: document.getElementById("todayBtn")
  };

  var TRANSLATOR_LABELS = {
    google: "Google 翻译",
    mymemory: "MyMemory 翻译",
    bundled: "内置摘要",
    cache: "已缓存",
    none: "原文"
  };

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function setText(node, text) {
    node.textContent = text == null ? "" : text;
  }

  function formatDate(iso) {
    if (!iso) return "—";
    var d = new Date(iso + "T00:00:00");
    if (isNaN(d.getTime())) return iso;
    return d.getFullYear() + "年" + (d.getMonth() + 1) + "月" + d.getDate() + "日";
  }

  function render(data) {
    // 正面剧照
    if (data.image) {
      el.hero.style.backgroundImage = "url(" + JSON.stringify(data.image) + ")";
    } else {
      el.hero.style.backgroundImage =
        "linear-gradient(135deg, #2a2450, #12142b), radial-gradient(circle at 70% 20%, #e8c15a55, transparent 50%)";
    }

    var titleZh = data.title_zh ? data.title + " · " + data.title_zh : data.title;
    setText(el.title, titleZh);
    setText(el.backTitle, titleZh);
    setText(el.composer, (data.composer || "") + (data.year ? "  ·  " + data.year : ""));
    setText(el.yearChip, data.year ? String(data.year) : "Musical");

    if (data.date) {
      setText(el.datePill, formatDate(data.date) + " · 今日片单 " + (data.index + 1) + "/" + data.total);
    }

    // 简介
    setText(el.intro, data.intro_zh || "暂无简介。");
    var tLabel = TRANSLATOR_LABELS[data.translator] || data.translator || "原文";
    setText(el.translatorTag, tLabel);

    // 图集
    el.gallery.innerHTML = "";
    if (Array.isArray(data.gallery) && data.gallery.length) {
      el.gallery.hidden = false;
      data.gallery.forEach(function (url) {
        var img = document.createElement("img");
        img.src = url;
        img.alt = data.title;
        img.loading = "lazy";
        el.gallery.appendChild(img);
      });
    } else {
      el.gallery.hidden = true;
    }

    // 背面链接
    setHref(el.officialBtn, data.official_url);
    setHref(el.feverBtn, data.fever_url);
    setHref(el.wikiBtn, data.wiki_url);

    document.title = (titleZh || "每日音乐剧") + " · Spinning Top";
  }

  function setHref(a, url) {
    if (url) {
      a.href = url;
      a.style.display = "";
    } else {
      a.href = "#";
      a.style.display = "none";
    }
  }

  function showError(message) {
    setText(el.intro, message || "加载失败，请稍后重试。");
    setText(el.translatorTag, "错误");
    setText(el.title, "加载失败");
  }

  function load() {
    el.card.classList.add("loading");
    fetch("/api/musical?offset=" + state.offset)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        el.card.classList.remove("loading");
        if (data && data.error) { showError(data.error); return; }
        render(data);
      })
      .catch(function () {
        el.card.classList.remove("loading");
        showError("网络请求失败，请确认 python app.py 正在运行。");
      });
  }

  /* 翻转：单击卡片（但不包括背面链接） */
  el.card.addEventListener("click", function (e) {
    if (e.target.closest("a")) return; // 点击链接直接打开，不翻转
    el.card.classList.toggle("flipped");
  });

  /* 滚轮向下隐藏提示 */
  el.frontBody.addEventListener("scroll", function () {
    if (el.frontBody.scrollTop > 14) {
      el.scrollHint.classList.add("hidden");
    } else {
      el.scrollHint.classList.remove("hidden");
    }
  });

  /* 日期导航 */
  el.prevBtn.addEventListener("click", function () {
    state.offset -= 1;
    resetCard();
    load();
  });

  el.nextBtn.addEventListener("click", function () {
    state.offset += 1;
    resetCard();
    load();
  });

  el.todayBtn.addEventListener("click", function () {
    state.offset = 0;
    resetCard();
    load();
  });

  function resetCard() {
    el.card.classList.remove("flipped");
    el.frontBody.scrollTop = 0;
    el.scrollHint.classList.remove("hidden");
  }

  load();
})();
