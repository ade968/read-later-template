(function () {
  "use strict";
  var el = document.getElementById("library-data");
  if (!el) return;
  var payload;
  try {
    payload = JSON.parse(el.textContent);
  } catch (err) {
    return;
  }
  var DATA = Array.isArray(payload.items) ? payload.items : [];
  var TOPICS = Array.isArray(payload.topics) ? payload.topics : [];
  var savedLabel = payload.savedLabel || "Saved links";
  var locale = payload.locale || "en-GB";
  var timeZone = payload.timezone || "UTC";
  var cur = "All";
  var q = "";

  function hueFor(topic) {
    if (topic === savedLabel) return "saved";
    var i = TOPICS.indexOf(topic);
    if (i < 0) i = 0;
    return String(i % 8);
  }

  function fmt(ts) {
    var when = new Date(ts * 1000);
    try {
      return when.toLocaleDateString(locale, {
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: timeZone
      });
    } catch (err) {
      return when.toISOString().slice(0, 16).replace("T", " ");
    }
  }

  function isHttp(url) {
    if (typeof url !== "string") return false;
    if (!/^(https?):\/\//i.test(url)) return false;
    try {
      var parsed = new URL(url);
      return parsed.protocol === "http:" || parsed.protocol === "https:";
    } catch (err) {
      return false;
    }
  }

  function chips() {
    var box = document.getElementById("chips");
    box.replaceChildren();
    ["All"].concat(TOPICS).forEach(function (label) {
      var count = label === "All"
        ? DATA.length
        : DATA.filter(function (item) { return item.topic === label; }).length;
      if (!count) return;
      var button = document.createElement("button");
      button.type = "button";
      button.className = "chip" + (label === cur ? " on" : "");
      button.dataset.hue = label === "All" ? "all" : hueFor(label);
      button.setAttribute("aria-pressed", label === cur ? "true" : "false");
      button.textContent = label + " (" + count + ")";
      button.addEventListener("click", function () {
        cur = label;
        chips();
        render();
      });
      box.appendChild(button);
    });
  }

  function addTag(parent, text, className) {
    if (!text) return;
    var span = document.createElement("span");
    if (className) span.className = className;
    span.textContent = String(text);
    parent.appendChild(span);
  }

  function render() {
    var needle = q.toLowerCase();
    var rows = DATA.filter(function (item) {
      if (cur !== "All" && item.topic !== cur) return false;
      if (!needle) return true;
      var hay = [item.title, item.source, item.summary, item.tag].join(" ").toLowerCase();
      return hay.indexOf(needle) !== -1;
    });
    var list = document.getElementById("list");
    list.replaceChildren();
    if (!rows.length) {
      var empty = document.createElement("p");
      empty.className = "meta";
      empty.textContent = DATA.length ? "Nothing matches." : "No articles yet.";
      list.appendChild(empty);
      return;
    }
    rows.forEach(function (item) {
      var article = document.createElement("article");
      article.dataset.hue = hueFor(item.topic);
      var link = document.createElement("a");
      link.textContent = item.title || item.url || "";
      if (isHttp(item.url)) {
        link.href = item.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
      }
      article.appendChild(link);
      if (item.summary) {
        var summary = document.createElement("div");
        summary.className = "sum";
        summary.textContent = String(item.summary);
        article.appendChild(summary);
      }
      var tags = document.createElement("div");
      tags.className = "tags";
      addTag(tags, item.source);
      addTag(tags, item.country);
      addTag(tags, item.region);
      addTag(tags, item.topic, "topic");
      addTag(tags, item.tag);
      addTag(tags, fmt(item.ts));
      article.appendChild(tags);
      list.appendChild(article);
    });
  }

  document.getElementById("q").addEventListener("input", function (event) {
    q = event.target.value || "";
    render();
  });
  chips();
  render();
})();
