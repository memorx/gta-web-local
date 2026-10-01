/* GTA Web Local: fill layer for the GTA IV pages.
 * In the game, several blocks of these pages are filled by a script at run time
 * (love-meet profiles, news, mail, LCPD records, adverts...).
 * The converter leaves them as <span class="scriptobj" data-name="...">; this fills
 * them with the game's own texts and textures (see _fill/data.js).
 */
(function () {
  "use strict";
  var me = document.currentScript;
  var SITE = me.getAttribute("data-site") || "";
  var PAGE = (me.getAttribute("data-page") || "").split("/").pop();
  var ROOT = me.getAttribute("data-root") || "";
  var D = window.LIBERTY;
  if (!D) return;
  var Q = new URLSearchParams(location.search);

  // ------------------------------------------------------------ helpers
  function slot(name) { return document.querySelector('.scriptobj[data-name="' + name + '"]'); }
  function slotsOf(prefix) {
    return Array.prototype.slice.call(document.querySelectorAll(".scriptobj"))
      .filter(function (e) { return e.getAttribute("data-name").replace(/_?\d+$/, "") === prefix; })
      .sort(function (a, b) { return num(a) - num(b); });
    function num(e) { var m = e.getAttribute("data-name").match(/(\d+)$/); return m ? +m[1] : 0; }
  }
  function asset(p) { return p ? ROOT + String(p).replace(/^@base\//, "") : ""; }
  function siteHref(site, page) { return ROOT + site + "/" + (page || "index.html"); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  // The game texts contain <br/> and <a href="www.site.com">: they are kept and the links rewritten.
  function rich(s) {
    return String(s == null ? "" : s)
      .replace(/<(?!\/?(br|a)\b)[^>]*>/gi, "")
      .replace(/<a\s+href="([^"]+)"\s*>/gi, function (_, u) { return '<a href="' + gameLink(u) + '">'; });
  }
  function gameLink(u) {
    u = u.replace(/^https?:\/\//, "").replace(/\\/g, "/");
    var parts = u.split("/"), site = parts[0], rest = parts.slice(1).join("/");
    if (!/\./.test(site)) return u;
    if (!/^www\./.test(site) && site.split(".").length === 2) site = "www." + site;
    if (rest && !/\.html?$/.test(rest)) rest += ".html";
    return siteHref(site, rest || "index.html");
  }
  function set(el, htmlStr) { if (el) { el.innerHTML = htmlStr; el.classList.add("lw-filled"); } return el; }
  function paras(list) { return (list || []).map(function (p) { return "<p>" + rich(p) + "</p>"; }).join(""); }
  // A choice that is stable for a day: it changes from one day to the next, not on every reload.
  var DAY = Math.floor(Date.now() / 86400000);
  function seeded(seed) { var x = (seed * 9301 + 49297) % 233280; return function () { x = (x * 9301 + 49297) % 233280; return x / 233280; }; }
  function shuffled(arr, salt) {
    var r = seeded(DAY * 31 + (salt || 0)), a = arr.slice();
    for (var i = a.length - 1; i > 0; i--) { var j = Math.floor(r() * (i + 1)); var t = a[i]; a[i] = a[j]; a[j] = t; }
    return a;
  }
  function hereWith(params) {
    var q = new URLSearchParams(location.search);
    Object.keys(params).forEach(function (k) { if (params[k] == null) q.delete(k); else q.set(k, params[k]); });
    var s = q.toString();
    return location.pathname.split("/").pop() + (s ? "?" + s : "");
  }
  function samePage(page, params) {
    var q = new URLSearchParams(params || {}).toString();
    return page + (q ? "?" + q : "");
  }

  // ------------------------------------------------------------ global fixes
  function globalFixes() {
    // "BACK" / back.html: in the game it goes back to the previous page.
    Array.prototype.forEach.call(document.querySelectorAll('a[href$="back.html"]'), function (a) {
      a.setAttribute("href", "javascript:history.back()");
    });
  }

  // ------------------------------------------------------------ adverts
  function adSmall(el, ad) {
    if (!el || !ad) return;
    set(el, '<a class="lw-ad" href="' + siteHref(ad.site) + '"><img src="' + asset(ad.small) + '" width="128" alt="' + esc(ad.site) + '"></a>');
  }
  function adMedium(el, ad) {
    if (!el || !ad) return;
    set(el, '<a class="lw-ad" href="' + siteHref(ad.site) + '"><img src="' + asset(ad.medium || ad.small) + '" width="176" alt="' + esc(ad.site) + '"></a>');
  }
  function fillAds(salt) {
    var ads = shuffled((D.ads || []).filter(function (a) { return a.site !== "www." + SITE.replace(/^www\./, "") && a.site !== SITE; }), salt);
    slotsOf("advert_small").forEach(function (el, i) { adSmall(el, ads[i % ads.length]); });
    slotsOf("advert_medium").forEach(function (el, i) { adMedium(el, ads[(i + 5) % ads.length]); });
    var xl = shuffled(D.xl || [], salt + 7);
    slotsOf("advert_xlarge").forEach(function (el, i) {
      var x = xl[i % xl.length]; if (!x) return;
      set(el, '<a class="lw-ad" href="' + siteHref(x.site) + '"><img src="' + asset(x.img) + '" width="404" alt="' + esc(x.site) + '"></a>');
    });
  }

  // ------------------------------------------------------------ news
  function newsList(key) { return (D.news && D.news[key]) || []; }
  function findStory(list) {
    var id = Q.get("s");
    for (var i = 0; i < list.length; i++) if (list[i].id === id) return { st: list[i], i: i };
    return { st: list[0], i: 0 };
  }
  function quickLinks(el, list, cur, page, n) {
    if (!el) return;
    n = n || 8;
    var start = Math.max(0, Math.min(cur - 2, list.length - n));
    var items = list.slice(start, start + n).map(function (st, k) {
      var idx = start + k;
      return '<li' + (idx === cur ? ' class="lw-cur"' : "") + '><a href="' + samePage(page, { s: st.id }) + '">' + esc(st.head) + "</a></li>";
    }).join("");
    var nav = '<div class="lw-qnav">' +
      (start > 0 ? '<a href="' + samePage(page, { s: list[Math.max(0, cur - n)].id }) + '">&laquo; newer</a>' : "") +
      (start + n < list.length ? '<a href="' + samePage(page, { s: list[Math.min(list.length - 1, cur + n)].id }) + '">older &raquo;</a>' : "") + "</div>";
    set(el, '<ul class="lw-quick">' + items + "</ul>" + nav);
  }
  function storyBody(st, first, rest) {
    // paragraph 0 in the first slot, the rest spread over the following ones
    set(first, paras(st.paras.slice(0, 1)));
    rest.forEach(function (el, i) {
      var p = i === rest.length - 1 ? st.paras.slice(i + 1) : st.paras.slice(i + 1, i + 2);
      if (p.length) set(el, paras(p)); else el.classList.add("lw-filled", "lw-empty-ok");
    });
  }

  function weazel() {
    var list = newsList("weazel");
    if (!list.length) return;
    if (PAGE === "news") {
      var f = findStory(list), st = f.st;
      set(slot("headline"), esc(st.head));
      set(slot("sec_headline"), esc(st.sub));
      set(slot("reporter"), esc(st.reporter || "Weazel News"));
      set(slot("photo"), st.photo ? '<img class="lw-photo" src="' + asset(st.photo) + '" width="330">' : (st.summary ? '<p class="lw-summary">' + esc(st.summary) + "</p>" : ""));
      storyBody(st, slot("story"), ["newsStory1", "newsStory2", "newsStory3", "newsStory4", "newsStory5"].map(slot).filter(Boolean));
      quickLinks(slot("quick_link_table"), list, f.i, "news.html", 10);
    } else {
      // front page: the most recent story with a photo (some in the game have none)
      var top = list.slice(0, 4).filter(function (s) { return s.photo; })[0] || list[0];
      set(slot("headline"), '<a href="news.html?s=' + top.id + '">' + esc(top.head) + "</a>");
      set(slot("secheadline"), esc(top.sub));
      set(slot("summary"), esc(top.summary || top.paras[0].slice(0, 180) + "…") + ' <a class="lw-more" href="news.html?s=' + top.id + '">MORE</a>');
      set(slot("photo"), top.photo ? '<a href="news.html?s=' + top.id + '"><img class="lw-photo" src="' + asset(top.photo) + '" width="256"></a>' : "");
      var w = (D.misc.weather || [])[DAY % 8];
      if (w) {
        set(slot("weatherPic"), '<img src="' + asset(w.img) + '" width="156" height="128" alt="">');
        set(slot("weatherText"), esc(w.text));
      }
    }
    fillAds(3);
  }

  function libtree() {
    var list = newsList("libtree");
    if (!list.length) return;
    if (PAGE === "news") {
      var f = findStory(list), st = f.st;
      set(slot("top_info"), "<b>" + esc(st.head) + "</b>" + (st.sub ? "<br>" + esc(st.sub) : ""));
      set(slot("photo"), st.photo ? '<img class="lw-photo" src="' + asset(st.photo) + '" width="348">' : (st.summary ? '<p class="lw-summary">' + esc(st.summary) + "</p>" : ""));
      set(slot("reporter"), esc(st.reporter || "Staff Writer"));
      storyBody(st, slot("newsStory"), ["newsStory1", "newsStory2", "newsStory3", "newsStory4", "newsStory5"].map(slot).filter(Boolean));
      quickLinks(slot("quick_link_table"), list, f.i, "news.html", 8);
    } else {
      var top = list.filter(function (s) { return s.home; })[0] || list[0];
      set(slot("home_news_photo"), top.home ? '<a href="news.html?s=' + top.id + '"><img src="' + asset(top.home) + '" width="176" height="176"></a>' : "");
      set(slot("home_news_info"), '<a class="lw-hl" href="news.html?s=' + top.id + '">' + esc(top.head) + "</a><br>" + esc(top.sub || top.summary));
      quickLinks(slot("quick_link_table"), list, list.indexOf(top), "news.html", 6);
      var day = (new Date()).getDay();
      set(slot("LCPD_blotter"), '<a href="' + siteHref("www.libertycitypolice.com") + '"><img src="' + asset(D.misc.blotter[day]) + '" width="176"></a>');
      var tv = shuffled(D.tv || [], 11)[0];
      if (tv) set(slot("TV_tonight"), '<img src="' + asset(tv) + '" width="176">');
    }
    fillAds(5);
  }

  function publib() {
    var list = newsList("publib");
    if (!list.length) return;
    var f = findStory(list), st = f.st;
    set(slot("headline"), esc(st.head));
    set(slot("sec_headline"), esc(st.sub));
    set(slot("reporter"), esc(st.reporter || "Staff"));
    storyBody(st, slot("news_story"), ["newsStory1", "newsStory2", "newsStory3", "newsStory4", "newsStory5"].map(slot).filter(Boolean));
    quickLinks(slot("quick_link_table"), list, f.i, "index.html", 10);
    fillAds(7);
  }

  // ------------------------------------------------------------ eyefind
  function eyefind() {
    set(slot("userName"), esc(D.player));
    var total = (D.mail || []).reduce(function (n, s) { return n + s.emails.length; }, 0);
    set(slot("totalEmails"), '<a href="' + siteHref("mail.eyefind.info") + '">' + total + " EMAILS</a>");
    var lt = newsList("libtree")[0];
    if (lt) set(slot("libTreeLink"), '<a class="lw-hl" href="' + siteHref("www.libertytreeonline.com", "news.html?s=" + lt.id) + '">' + esc(lt.head) + "</a><br>" + esc(lt.sub));
    var tv = shuffled(D.tv || [], 2);
    slotsOf("tvAdvert").forEach(function (el, i) { if (tv[i]) set(el, '<img src="' + asset(tv[i]) + '" width="128">'); });
    fillAds(1);
    // LuckyFind: random results on every search
    var res = (D.search || []).slice();
    for (var i = res.length - 1; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)); var t = res[i]; res[i] = res[j]; res[j] = t; }
    slotsOf("randomSearch").forEach(function (el, k) {
      var r = res[k]; if (!r) return;
      var href = gameLink(r.u);
      set(el, '<div class="lw-sr"><a class="lw-sr-t" href="' + href + '">' + esc(r.t) + '</a><div class="lw-sr-d">' + esc(r.d) + '</div><div class="lw-sr-u">' + esc(r.u) + "</div></div>");
    });
    set(slot("errorBox"), '<div class="lw-err">' + esc(D.misc.serverNotFound) + "</div>");
    // "SEARCH AGAIN" (link "1") draws the results again
    Array.prototype.forEach.call(document.querySelectorAll('a[href="1.html"]'), function (a) { a.setAttribute("href", "search.html"); });
  }

  // ------------------------------------------------------------ mail
  function mail() {
    var senders = D.mail || [], all = [];
    senders.forEach(function (s, si) { s.emails.forEach(function (e, ei) { all.push({ s: s, e: e, id: si + "_" + ei }); }); });
    var per = 12, page = Math.max(0, +(Q.get("p") || 0)), pages = Math.max(1, Math.ceil(all.length / per));
    page = Math.min(page, pages - 1);
    var read = {};
    try { read = JSON.parse(localStorage.getItem("lw-read-" + D.ep) || "{}"); } catch (e) { }
    var unread = all.filter(function (m) { return !read[m.id]; }).length;
    set(slot("emailTopInfo"), "<b>" + esc(D.player) + "</b> &middot; " + all.length + " EMAILS &middot; " + unread + " UNREAD");
    // The emailInbox0..5 rows are templates the game draws on top; the inbox goes in the main window.
    slotsOf("emailInbox").forEach(function (el) { el.classList.add("lw-filled", "lw-empty-ok", "lw-hide"); });
    var sel = all.filter(function (m) { return m.id === Q.get("m"); })[0];
    var main = slot("emailMainWindow");
    if (sel) {
      read[sel.id] = 1;
      try { localStorage.setItem("lw-read-" + D.ep, JSON.stringify(read)); } catch (e) { }
      var rep = sel.e.replies.map(function (r, i) {
        return '<details class="lw-reply"><summary>' + (i === 0 ? "REPLY (+)" : "REPLY (&minus;)") + "</summary><p>" + rich(r) + "</p></details>";
      }).join("");
      set(main, '<div class="lw-mail"><a class="lw-mback" href="' + hereWith({ m: null }) + '">&laquo; INBOX</a>' +
        '<div class="lw-mhead"><b>From:</b> ' + esc(sel.s.name) + " (" + esc(sel.s.addr) + ")<br><b>Subject:</b> " + esc(sel.e.subj) +
        '</div><div class="lw-mbody">' + rich(sel.e.body).replace(/\n/g, "<br>") + "</div>" + rep + "</div>");
    } else {
      var rows = all.slice(page * per, page * per + per).map(function (m) {
        return '<a class="lw-mrow' + (read[m.id] ? "" : " lw-unread") + '" href="' + hereWith({ m: m.id, p: page }) + '">' +
          '<span class="lw-mdot">' + (read[m.id] ? "" : "&#9679;") + '</span><span class="lw-mfrom">' + esc(m.s.name) + '</span><span class="lw-msubj">' + esc(m.e.subj || "(no subject)") + "</span></a>";
      }).join("");
      set(main, '<div class="lw-mail lw-inbox"><div class="lw-mhead"><b>INBOX</b> &middot; page ' + (page + 1) + " / " + pages + "</div>" + rows + "</div>");
    }
    ["emailMainWindow2", "emailMainWindow3"].forEach(function (n) { var e = slot(n); if (e) e.classList.add("lw-filled", "lw-empty-ok", "lw-hide"); });
    set(slot("navTopTitle"), page > 0 ? '<a href="' + hereWith({ p: page - 1, m: null }) + '">NEWER</a>' : "NEWER");
    set(slot("navBottomTitle"), page < pages - 1 ? '<a href="' + hereWith({ p: page + 1, m: null }) + '">OLDER</a>' : "OLDER");
    set(slot("navTopImage"), page > 0 ? '<a href="' + hereWith({ p: page - 1, m: null }) + '"><img src="imgs/but_up.png" width="16" height="16" alt="up"></a>' : "");
    set(slot("navBottomImage1"), page < pages - 1 ? '<a href="' + hereWith({ p: page + 1, m: null }) + '"><img src="imgs/but_down.png" width="16" height="16" alt="down"></a>' : "");
    ["navTopImage", "navBottomImage1"].forEach(function (n) { var e = slot(n); if (e && !e.innerHTML) e.classList.add("lw-empty-ok"); });
    var nb2 = slot("navBottomImage2"); if (nb2) nb2.classList.add("lw-filled", "lw-empty-ok");
    set(slot("emailBottomInfo"), "eyefind mail");
  }

  // ------------------------------------------------------------ love-meet
  function lovemeet() {
    var LM = D.lovemeet;
    function profHref(g, i) { return "profile.html?g=" + g + "&i=" + i; }
    if (PAGE === "femaleprofiles" || PAGE === "maleprofiles") {
      var g = PAGE === "femaleprofiles" ? "f" : "m", list = LM[g] || [], cards = slotsOf("miniProfile");
      var page = +(Q.get("p") || 0), per = cards.length;
      cards.forEach(function (el, k) {
        var i = page * per + k, p = list[i];
        if (!p) { el.classList.add("lw-filled", "lw-empty-ok"); return; }
        set(el, '<a class="lw-card" href="' + profHref(g, i) + '"><img src="' + asset(p.photo) + '" width="160" alt="">' +
          '<span class="lw-card-user">' + esc(p.user) + '</span><span class="lw-card-meta">' + esc(p.age) + " &middot; " + esc(p.loc) + "</span>" +
          '<span class="lw-card-quote">&ldquo;' + esc(p.quote) + "&rdquo;</span></a>");
      });
      if (list.length > per && cards.length) {
        var nav = document.createElement("div");
        nav.className = "lw-pager";
        nav.innerHTML = page > 0 ? '<a href="' + hereWith({ p: page - 1 }) + '">&laquo; BACK</a>' : '<a href="' + hereWith({ p: page + 1 }) + '">MORE &raquo;</a>';
        var table = cards[cards.length - 1].closest("table");
        if (table) table.parentNode.insertBefore(nav, table.nextSibling);
      }
    } else if (PAGE === "profile") {
      var g2 = Q.get("g") === "m" ? "m" : "f", i2 = Math.max(0, Math.min(11, +(Q.get("i") || 0))), p2 = (LM[g2] || [])[i2];
      if (!p2) return;
      document.title = "LOVE MEET - " + p2.user;
      set(slot("profilePhoto"), '<img src="' + asset(p2.photo) + '" width="164" alt="">');
      set(slot("profileUser"), esc(p2.user));
      set(slot("profileAge"), "AGE: " + esc(p2.age));
      set(slot("profileLoc"), esc(p2.loc));
      set(slot("profileJob"), esc(p2.job));
      set(slot("profileSex"), esc(p2.sex));
      set(slot("profileBuild"), esc(p2.build));
      set(slot("profileAbout"), rich(p2.about));
      set(slot("profileLike"), rich(p2.likes));
      set(slot("profileDislike"), rich(p2.dislikes));
      set(slot("profileBack"), '<a href="' + (g2 === "f" ? "femaleprofiles.html" : "maleprofiles.html") + (i2 >= 9 ? "?p=1" : "") + '">&laquo; BACK</a>');
      set(slot("profileDate"), '<button type="button" class="lw-btn" id="lw-date">DATE</button><span class="lw-note" id="lw-date-msg"></span>');
      var b = document.getElementById("lw-date");
      if (b) b.onclick = function () { document.getElementById("lw-date-msg").textContent = " Message Sent"; b.disabled = true; };
    } else {
      // front page: the "true love" of the day
      var both = (LM.f || []).map(function (p, i) { return { p: p, g: "f", i: i }; }).concat((LM.m || []).map(function (p, i) { return { p: p, g: "m", i: i }; }));
      var pick = shuffled(both, 21)[0];
      if (pick) {
        set(slot("trueLovePic"), '<a href="' + profHref(pick.g, pick.i) + '"><img src="' + asset(pick.p.eyes) + '" width="232" alt=""></a>');
        set(slot("trueLoveQuote"), "&ldquo;" + esc(pick.p.quote) + "&rdquo;");
        set(slot("trueLoveUser"), '<a href="' + profHref(pick.g, pick.i) + '">' + esc(pick.p.user) + "</a>, " + esc(pick.p.age) + ", " + esc(pick.p.loc));
      }
    }
  }

  // ------------------------------------------------------------ LCPD
  function lcpd() {
    // lists A-E, F-J...: the numeric link is the id of the record
    Array.prototype.forEach.call(document.querySelectorAll("a[href]"), function (a) {
      var m = a.getAttribute("href").match(/^(\d+)\.html$/);
      if (m && D.lcpd[m[1]]) a.setAttribute("href", "profile.html?id=" + m[1]);
    });
    if (PAGE !== "profile") return;
    var r = D.lcpd[Q.get("id")];
    if (!r) {
      set(slot("surname"), "<i>Select a record from the database.</i>");
      ["status", "forename", "age", "birth", "affiliations", "rapsheet", "notes"].forEach(function (n) { var e = slot(n); if (e) e.classList.add("lw-filled", "lw-empty-ok"); });
      return;
    }
    set(slot("surname"), esc(r.s));
    var st = slot("status"); if (st) st.classList.add("lw-filled", "lw-empty-ok");
    set(slot("forename"), esc(r.f));
    set(slot("age"), esc(r.age));
    set(slot("birth"), esc(r.birth));
    set(slot("affiliations"), rich(r.aff));
    set(slot("rapsheet"), rich(r.rap));
    set(slot("notes"), rich(r.notes));
  }

  // ------------------------------------------------------------ VIP ringtones
  function vip() {
    var V = D.vip, names = V.names || {};
    Array.prototype.forEach.call(document.querySelectorAll("a[href]"), function (a) {
      var m = a.getAttribute("href").match(/^(\d+)\.html$/);
      if (!m) return;
      var n = +m[1];
      if (PAGE === "themes") a.setAttribute("href", "purchase.html?theme=" + n);
      else if (n >= 1000) a.setAttribute("href", "purchase.html?ring=" + (n - 1000));
      else { a.setAttribute("href", "javascript:void 0"); a.title = "Preview not available outside the game"; a.classList.add("lw-nolink"); }
    });
    function ringRow(el, id) {
      if (!el || id == null) return;
      set(el, '<a class="lw-ring" href="purchase.html?ring=' + id + '">' + esc(names[id] || "Ringtone " + id) + "</a>");
    }
    var mp3 = (V.lists && V.lists.mp3) || [], sfx = (V.lists && V.lists.sfx) || [];
    // On the front page the "mono" slots go under TOP MP3 and the "poly" ones under TOP SFX.
    slotsOf("mono").forEach(function (el, i) { ringRow(el, mp3[i]); });
    slotsOf("poly").forEach(function (el, i) { ringRow(el, sfx[i]); });
    slotsOf("theme").forEach(function (el, i) {
      set(el, '<a href="purchase.html?theme=' + (i + 1) + '"><img src="' + asset("_tex/webthemesvip/webtheme_" + (i + 1) + ".png") + '" width="72" height="72" alt=""></a>');
    });
    if (PAGE === "purchase") {
      var th = Q.get("theme"), rg = Q.get("ring");
      if (th) {
        set(slot("purchase_icon"), '<img src="' + asset("_tex/webthemesvip/webtheme_" + (+th) + ".png") + '" width="120" height="120" alt="">');
        set(slot("purchase_text"), "<b>" + esc(V.msg.thanks) + "</b><br>" + esc(V.msg.themeSent));
      } else if (rg) {
        set(slot("purchase_icon"), '<img src="imgs/speaker.png" width="64" height="64" alt="">');
        set(slot("purchase_text"), "<b>" + esc(names[rg] || "") + "</b><br>" + esc(V.msg.thanks) + "<br>" + esc(V.msg.ringSent));
      } else {
        set(slot("purchase_icon"), '<img src="imgs/logo.png" width="120" alt="">');
        set(slot("purchase_text"), "Choose a ringtone or a theme to buy.");
      }
    }
  }

  // ------------------------------------------------------------ blogs
  function blog(posts, textPrefix, navName) {
    var el = slotsOf(textPrefix), per = el.length || 6;
    var pages = Math.max(1, Math.ceil(posts.length / per)), page = Math.min(pages - 1, Math.max(0, +(Q.get("p") || 0)));
    el.forEach(function (e, k) {
      var p = posts[page * per + k];
      if (!p) { e.classList.add("lw-filled", "lw-empty-ok"); return; }
      set(e, '<div class="lw-post">' + paras(p) + "</div>");
    });
    set(slot(navName), '<span class="lw-blognav">' +
      (page < pages - 1 ? '<a href="' + hereWith({ p: page + 1 }) + '">' + esc(D.misc.prevPosts) + "</a> " : "") +
      (page > 0 ? '<a href="' + hereWith({ p: page - 1 }) + '">' + esc(D.misc.nextPosts) + "</a>" : "") + "</span>");
  }

  // ------------------------------------------------------------ craplist
  function craplist() {
    var A = D.misc.alexAd || {};
    if (PAGE === "womenseekingmen") {
      set(slot("alexLink"), '<a href="womenseekingmen13.html">' + esc(A.title) + "</a> " + esc(A.loc));
    } else if (PAGE === "womenseekingmen13") {
      set(slot("alexInfo"), paras(A.info));
      set(slot("alexLink"), '<a href="' + siteHref("mail.eyefind.info") + '">' + esc(A.contact || "Contact me") + "</a>");
    }
  }

  // ------------------------------------------------------------ Goldberg (resume)
  function goldberg() {
    var G = D.misc.gland || {}, el = slot("glandScriptObject");
    if (!el) return;
    set(el, '<button type="button" class="lw-btn" id="lw-resume">' + esc(G.submit) + '</button><div class="lw-note" id="lw-resume-msg"></div>');
    document.getElementById("lw-resume").onclick = function () {
      document.getElementById("lw-resume-msg").textContent = G.thanks; this.disabled = true;
    };
  }

  // ------------------------------------------------------------ internet cafe desktop
  function desktop() {
    set(slot("iconWEB"), '<a class="lw-icon" href="' + siteHref("www.eyefind.info") + '"><img src="imgs/butinternet.png" width="44" height="44" alt=""><br>INTERNET</a>');
    set(slot("iconLOGOUT"), '<a class="lw-icon" href="/"><img src="imgs/butlogout.png" width="44" height="44" alt=""><br>LOGOUT</a>');
    // HDgap hangs directly from a <table>: the browser moves it before the table. It is left empty.
    var gap = slot("HDgap"); if (gap) gap.classList.add("lw-filled", "lw-empty-ok", "lw-hide");
  }

  // ------------------------------------------------------------ Celebinator (TBoGT)
  function celeb() {
    var C = D.celeb || { posts: [] };
    if (PAGE === "comment") {
      var i = Math.max(0, +(Q.get("i") || 0)), p = C.posts[i] || C.posts[0];
      if (p) set(slot("celebPost"), '<div class="lw-post"><h3>' + esc(p.title) + "</h3>" + paras(p.paras) + "</div>");
      set(slot("celebComment"), '<textarea class="lw-ta" rows="4" placeholder="Your comment"></textarea>');
      set(slot("celebSubmit"), '<button type="button" class="lw-btn" onclick="this.disabled=true;this.nextSibling.textContent=\' Message Sent\'">SUBMIT</button><span class="lw-note"></span>');
    } else {
      slotsOf("celebPost").forEach(function (el, k) {
        var p = C.posts[k];
        if (!p) { el.classList.add("lw-filled", "lw-empty-ok"); return; }
        set(el, '<div class="lw-post"><h3>' + esc(p.title) + "</h3>" + paras(p.paras) + '<a class="lw-more" href="comment.html?i=' + k + '">COMMENT</a></div>');
      });
    }
  }

  // ------------------------------------------------------------ dispatch by site
  var ROUTES = {
    "www.eyefind.info": eyefind,
    "mail.eyefind.info": mail,
    "www.weazelnews.com": weazel,
    "www.libertytreeonline.com": libtree,
    "www.publiclibertyonline.com": publib,
    "www.love-meet.net": lovemeet,
    "www.libertycitypolice.com": lcpd,
    "www.vipluxuryringtones.com": vip,
    "liberatedwoman.blogsnobs.org": function () { blog(D.blogs.alex, "alexBogText", "alexBlogNav"); },
    "eddielowfilthslayer.blogsnobs.org": function () { blog(D.blogs.eddie, "edBlogText", "eddieBlogNav"); },
    "www.craplist.net": craplist,
    "www.goldberglignerandshyster.com": goldberg,
    "hidden": desktop,
    "www.youvebeencelebinated.com": celeb,
    // The Our Own Reality front page is empty: the game opens one of its editions (a1..e4).
    "www.our-own-reality.com": function () { if (PAGE === "index" && !document.body.textContent.trim()) location.replace("a1.html"); },
  };

  function run() {
    globalFixes();
    try { (ROUTES[SITE] || function () { })(); } catch (e) { console.error("[liberty-fill]", SITE, PAGE, e); }
    // any other site with advert slots (americantravelguide, etc.)
    if (!ROUTES[SITE] || ["www.eyefind.info", "www.weazelnews.com", "www.libertytreeonline.com", "www.publiclibertyonline.com"].indexOf(SITE) < 0) {
      if (document.querySelector('.scriptobj[data-name^="advert_"]:not(.lw-filled)')) fillAds(9);
    }
    document.documentElement.classList.add("lw-ready");
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run); else run();
})();
