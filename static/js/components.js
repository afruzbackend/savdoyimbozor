/* Alpine.js komponentlari — custom, ARIA + klaviatura bilan. Brauzer default'lari yo'q. */
(function () {
  const UZ_MONTHS = ["Yanvar","Fevral","Mart","Aprel","May","Iyun","Iyul",
    "Avgust","Sentabr","Oktabr","Noyabr","Dekabr"];
  const UZ_WD = ["Du","Se","Cho","Pa","Ju","Sh","Ya"]; // Dushanbadan
  // Tilga qarab oy/hafta nomlari (kalendar uchun)
  const _MONTHS = {
    cyrl: ["Январ","Феврал","Март","Апрел","Май","Июн","Июл","Август","Сентабр","Октабр","Ноябр","Декабр"],
    ru: ["Январь","Февраль","Март","Апрель","Май","Июнь","Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"],
  };
  const _WD = { cyrl: ["Ду","Се","Чо","Па","Жу","Ша","Як"], ru: ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"] };
  function uiLang() {
    const m = document.cookie.match("(^|;)\\s*uilang\\s*=\\s*([^;]+)");
    return m ? m.pop() : "";
  }
  function calMonths() { return _MONTHS[uiLang()] || UZ_MONTHS; }
  function calWd() { return _WD[uiLang()] || UZ_WD; }

  // Summani "1 234 567" ko'rinishida formatlash
  function fmt(n) {
    n = String(n).replace(/\D/g, "");
    return n.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  }
  function unfmt(s) { return parseInt(String(s).replace(/\D/g, ""), 10) || 0; }
  // Grafik o'qi uchun ixcham pul formati — float axlati YO'Q (0, 5K, 1.2M)
  function moneyTick(v) {
    v = Math.round(Number(v) || 0);
    var a = Math.abs(v);
    if (a >= 1000000) return (v / 1000000).toFixed(a % 1000000 ? 1 : 0) + "M";
    if (a >= 1000) return Math.round(v / 1000) + "K";
    return String(v);
  }
  window.BN = { fmt, unfmt, moneyTick, UZ_MONTHS, UZ_WD };

  function getCookie(name) {
    const m = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return m ? m.pop() : "";
  }

  // ---- Native <select.select-native> ni chiroyli custom dropdownga aylantirish ----
  // Shablon o'zgarmaydi; native select yashirin qoladi (forma POST ishlaydi).
  function enhanceSelect(sel) {
    if (sel.dataset.nsDone) return;
    sel.dataset.nsDone = "1";
    const wrap = document.createElement("div");
    wrap.className = "dropdown nice-select";
    sel.parentNode.insertBefore(wrap, sel);
    wrap.appendChild(sel);
    sel.classList.add("ns-native");

    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "dropdown-trigger";
    const lbl = document.createElement("span");
    trigger.appendChild(lbl);
    const chev = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    chev.setAttribute("class", "icon-sm");
    chev.innerHTML = '<use href="/static/icons/sprite.svg#i-chevron-down"></use>';
    trigger.appendChild(chev);
    wrap.appendChild(trigger);

    const panel = document.createElement("div");
    panel.className = "dropdown-panel";
    panel.hidden = true;
    const searchable = sel.options.length > 7;
    const search = document.createElement("input");
    search.className = "dropdown-search";
    search.placeholder = "Qidirish...";
    if (searchable) panel.appendChild(search);
    const list = document.createElement("div");
    panel.appendChild(list);
    wrap.appendChild(panel);

    function syncLabel() {
      const o = sel.options[sel.selectedIndex];
      lbl.textContent = o ? o.textContent.trim() : "Tanlang";
    }
    function render(q) {
      list.innerHTML = "";
      [...sel.options].forEach((o) => {
        if (o.disabled || o.value === "") return; // "Tanlang" placeholder — tanlab bo'lmaydi
        if (q && !o.textContent.toLowerCase().includes(q.toLowerCase())) return;
        const item = document.createElement("div");
        item.className = "option";
        item.textContent = o.textContent.trim();
        if (o.selected) item.setAttribute("aria-selected", "true");
        item.addEventListener("click", () => {
          sel.value = o.value;
          sel.dispatchEvent(new Event("change", { bubbles: true }));
          syncLabel();
          close();
        });
        list.appendChild(item);
      });
    }
    function open() {
      panel.hidden = false;
      if (searchable) {
        search.value = "";
        render("");
        // Faqat kompyuterda (sichqoncha) avtofokus — telefonda klaviatura chiqmasin
        var fine = window.matchMedia && window.matchMedia("(pointer:fine)").matches;
        if (fine) setTimeout(() => search.focus(), 30);
      }
    }
    function close() {
      panel.hidden = true;
    }
    trigger.addEventListener("click", () => (panel.hidden ? open() : close()));
    search.addEventListener("input", () => render(search.value));
    document.addEventListener("click", (e) => {
      if (!wrap.contains(e.target)) close();
    });
    sel.addEventListener("change", syncLabel); // barkod kabi tashqi o'zgarish uchun
    syncLabel();
    render("");
  }
  function enhanceSelects(root) {
    // Barcha `.select-native` -> maxsus dizayn dropdown (brauzer default'i emas).
    (root || document).querySelectorAll("select.select-native").forEach(enhanceSelect);
  }
  document.addEventListener("DOMContentLoaded", () => enhanceSelects());
  document.body &&
    document.body.addEventListener &&
    document.body.addEventListener("htmx:afterSwap", (e) => enhanceSelects(e.target));

  // ---- Forma validatsiyasi: bo'sh majburiy maydon QIZIL + aniq xabar ----
  function fieldLabel(el) {
    var f = el.closest(".field");
    var lab = f && f.querySelector(".label");
    var txt = lab ? lab.textContent : el.getAttribute("placeholder") || "Maydon";
    return txt.trim().replace(/[:*\s]+$/, "");
  }
  function errTarget(el) {
    // Maxsus dropdownga aylantirilgan select uchun — ko'rinadigan trigger qizil bo'lsin
    var wrap = el.closest && el.closest(".dropdown");
    if (!wrap && el.type === "hidden") wrap = el.closest(".field"); // sana va h.k. maxsus maydon
    return (wrap && wrap.querySelector(".dropdown-trigger")) || el;
  }
  function clearErr(el) {
    errTarget(el).classList.remove("err");
    var f = el.closest(".field");
    var m = f && f.querySelector(".field-err");
    if (m) m.remove();
  }
  function showErr(el) {
    errTarget(el).classList.add("err");
    var f = el.closest(".field");
    if (f && !f.querySelector(".field-err")) {
      var d = document.createElement("div");
      d.className = "field-err";
      d.textContent = fieldLabel(el) + " — to'ldiring";
      f.appendChild(d);
    }
  }
  function validateForm(form) {
    var first = null;
    var missing = [];
    form.querySelectorAll("[required]").forEach(function (el) {
      var box = el.closest(".field") || el;
      if (el.disabled || box.offsetParent === null) return; // yashirin/o'chirilgan — tekshirilmaydi
      var empty;
      if (el.type === "checkbox" || el.type === "radio") {
        empty = !form.querySelector('[name="' + el.name + '"]:checked');
      } else {
        empty = !String(el.value).trim();
      }
      if (empty) {
        showErr(el);
        missing.push(fieldLabel(el));
        if (!first) first = el;
      } else {
        clearErr(el);
      }
    });
    if (first) {
      first.scrollIntoView({ block: "center", behavior: "smooth" });
      try { first.focus({ preventScroll: true }); } catch (e) { first.focus(); }
      window.toast && window.toast("To'ldirilmagan: " + missing.join(", "), "bad");
      return false;
    }
    return true;
  }
  function initValidation(root) {
    (root || document).querySelectorAll("form").forEach(function (form) {
      if (form.__valInit) return;
      if ((form.getAttribute("method") || "").toLowerCase() === "get") return;
      if (form.hasAttribute("data-no-validate")) return;
      if (!form.querySelector("[required]")) return;
      form.__valInit = true;
      form.setAttribute("novalidate", "");
      form.addEventListener("submit", function (e) {
        if (!validateForm(form)) e.preventDefault();
      });
      form.addEventListener("input", function (e) {
        if (e.target.matches("[required]")) clearErr(e.target);
      });
      form.addEventListener("change", function (e) {
        if (e.target.matches("[required]")) clearErr(e.target);
      });
    });
  }
  document.addEventListener("DOMContentLoaded", function () { initValidation(); });
  document.body &&
    document.body.addEventListener &&
    document.body.addEventListener("htmx:afterSwap", function (e) { initValidation(e.target); });

  // ---- Jonli yangilanish: faqat foydalanuvchi tinch turganda; skroll joyi saqlanadi ----
  // (ilgari har 25s da to'liq reload bo'lib, o'qib turgan joy tepaga sakrardi)
  window.liveRefresh = function (ms) {
    var main = document.querySelector(".main");
    var key = "bn-scroll:" + location.pathname;
    try {
      var saved = sessionStorage.getItem(key);
      if (saved !== null && main) main.scrollTop = parseInt(saved, 10) || 0;
      sessionStorage.removeItem(key);
      // Avto-yangilanishdan keyin animatsiyalar qayta o'ynamasin (jim)
      if (sessionStorage.getItem("bn-quiet") === "1") {
        window.__bnQuiet = true;
        document.documentElement.classList.add("no-anim");
        if (window.Chart) window.Chart.defaults.animation = false;
      }
      sessionStorage.removeItem("bn-quiet");
    } catch (e) { /* storage yopiq bo'lishi mumkin */ }
    var last = Date.now();
    var mark = function () { last = Date.now(); };
    if (main) main.addEventListener("scroll", mark, { passive: true });
    ["click", "keydown", "touchstart", "input", "mousemove"].forEach(function (ev) {
      document.addEventListener(ev, mark, { passive: true, capture: true });
    });
    var timer = setInterval(function () {
      // Xodim uzoq qimirlamagan — avto-yangilash to'xtaydi, server sessiyani yopadi (xavfsizlik)
      if (window.BN_IDLE_MS && Date.now() - last > window.BN_IDLE_MS) { clearInterval(timer); return; }
      if (document.hidden) return;
      if (document.querySelector(".modal-backdrop:not([hidden])")) return;
      if (Date.now() - last < 20000) return; // foydalanuvchi faol — halaqit bermaymiz
      try {
        if (main) sessionStorage.setItem(key, String(main.scrollTop));
        sessionStorage.setItem("bn-quiet", "1");
      } catch (e) { /* ok */ }
      location.reload();
    }, ms || 30000);
  };

  // ---- Raqam maydoni: fokusda turganda g'ildirak qiymatni jimgina o'zgartirmasin ----
  // (sotuvchi narxni yozib, sahifani aylantirsa — 8000 → 7999 bo'lib saqlanib ketardi)
  document.addEventListener("wheel", function (e) {
    var el = document.activeElement;
    if (el && el.type === "number" && e.target === el) el.blur();
  }, { passive: true });

  // ---- Panel: parol katakchasi — qiymat faqat bosilganda serverdan (audit bilan) ----
  document.addEventListener("alpine:init", function () {
    window.Alpine.data("pwCell", function (url) {
      return {
        pw: "", url: url,
        async fetchPw() {
          var csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || "";
          var r = await fetch(this.url, { method: "POST", headers: { "X-CSRFToken": csrf } });
          var d = {};
          try { d = await r.json(); } catch (e) { /* bo'sh */ }
          if (!r.ok) { window.toast && window.toast(d.detail || "Parol olinmadi", "bad"); return ""; }
          return d.password || "";
        },
        async toggle() { this.pw = this.pw ? "" : await this.fetchPw(); },
        async copy() {
          var v = this.pw || await this.fetchPw();
          if (!v) return;
          try { await navigator.clipboard.writeText(v); window.toast && window.toast("Parol nusxalandi", "ok"); }
          catch (e) { this.pw = v; }  // nusxa ruxsati yo'q — ko'rsatib qo'yamiz
        },
      };
    });
  });

  // ---- Miqdor maydoni mahsulot birligiga qarab ----
  // dona/quti/bog'lam — butun son (qadam 1, raqam klaviaturasi); kg/litr/metr/qop — kasr (2,5 kg).
  // Bitta qadam qotirilsa yo 2,5 kg chirigan pomidor kiritilmas, yo 1,5 kurtka o'tib ketardi.
  // Birlik: select[name=product] tanlangan option[data-unit] (majburiy bo'lsa), aks holda
  // select[name=unit]. "Qop/quti hisobida" belgilansa — kasr mumkin (1,5 quti = 18 dona).
  // Server ham tekshiradi (catalog.models.whole_qty_error).
  var WHOLE_UNITS = { "dona": 1, "quti": 1, "bog'lam": 1 };
  function syncQty(form) {
    var qty = form && form.querySelector('input[name="quantity"]');
    if (!qty) return;
    var prod = form.querySelector('select[name="product"]');
    var opt = prod && prod.options[prod.selectedIndex];
    var unitSel = form.querySelector('select[name="unit"]');
    var unit = "";
    if (prod && prod.required && opt && opt.dataset.unit) unit = opt.dataset.unit;
    else if (unitSel && !(prod && prod.required)) unit = unitSel.value;
    var packs = form.querySelector('input[name="in_packs"]');
    var whole = !!WHOLE_UNITS[unit] && !(packs && packs.checked);
    qty.step = whole ? "1" : "0.001";
    qty.min = whole ? "1" : "0.001";
    qty.inputMode = whole ? "numeric" : "decimal";
    var lbl = form.querySelector("[data-qty-unit]");
    if (lbl) lbl.textContent = unit;
  }
  window.syncQty = syncQty;
  document.addEventListener("change", function (e) {
    if (e.target.form && /^(product|unit|in_packs)$/.test(e.target.name)) syncQty(e.target.form);
  });
  // Rejim almashsa (ro'yxatdan / yangi) — yozishni boshlashdan oldin yana moslanadi
  document.addEventListener("focusin", function (e) {
    if (e.target.name === "quantity" && e.target.form) syncQty(e.target.form);
  });
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll('form input[name="quantity"]').forEach(function (q) { syncQty(q.form); });
  });

  // ---- .field ichidagi yorliq ↔ maydon bog'lanishi (yorliq bosilsa fokus; ekran o'qigich) ----
  function linkLabels(root) {
    (root || document).querySelectorAll(".field").forEach(function (f, i) {
      var label = f.querySelector(":scope > label.label:not([for])");
      var ctl = f.querySelector(
        "input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=file]), textarea");
      if (!label || !ctl || label.contains(ctl)) return;
      if (!ctl.id) ctl.id = "fld-" + (ctl.name || "x") + "-" + i;
      label.htmlFor = ctl.id;
    });
  }
  document.addEventListener("DOMContentLoaded", function () { linkLabels(); });

  // ---- Skroll joyi xotirasi ----
  // .main (va [data-keep-scroll] bloklar) o'zi alohida skroll bloki — brauzer "Orqaga"da uni
  // TIKLAMAYDI: ro'yxatni pastga surib, do'konga kirib, qaytsangiz tepadan boshlanardi.
  // Tiklanadi: Orqaga/Oldinga, F5, va forma yuborilib o'sha sahifaga qaytilganda (POST → redirect).
  // Oddiy havola bilan yangi sahifa — tepadan (kutilgan xulq).
  (function () {
    var main = document.querySelector(".main");
    var here = location.pathname + location.search;
    var navType = "";
    try { navType = (performance.getEntriesByType("navigation")[0] || {}).type || ""; } catch (e) {}
    function sget(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } }
    function sset(k, v) { try { sessionStorage.setItem(k, v); } catch (e) { /* yopiq */ } }
    function sdel(k) { try { sessionStorage.removeItem(k); } catch (e) { /* yopiq */ } }
    function boxes() {
      var list = main ? [["main", main]] : [];
      document.querySelectorAll("[data-keep-scroll]").forEach(function (el) {
        list.push([el.getAttribute("data-keep-scroll"), el]);
      });
      return list;
    }
    function snapshot() {
      var s = {};
      boxes().forEach(function (b) { s[b[0]] = [b[1].scrollLeft, b[1].scrollTop]; });
      return s;
    }
    var target = null, afterPost = false;
    if (navType === "back_forward" || navType === "reload") {
      try { target = JSON.parse(sget("bn-pos:" + here) || "null"); } catch (e) { target = null; }
    }
    var ret = sget("bn-post-return");
    if (ret) {
      sdel("bn-post-return");
      try { ret = JSON.parse(ret); } catch (e) { ret = null; }
      if (ret && ret.path === location.pathname && Date.now() - ret.t < 30000) {
        target = ret.pos; afterPost = true;
      }
    }
    var userMoved = false;
    ["wheel", "touchmove", "keydown", "mousedown"].forEach(function (ev) {
      window.addEventListener(ev, function () { userMoved = true; }, { passive: true, capture: true });
    });
    function apply() {
      if (!target || userMoved) return;
      boxes().forEach(function (b) {
        var p = target[b[0]];
        if (p) { b[1].scrollLeft = p[0]; b[1].scrollTop = p[1]; }
      });
    }
    apply();
    // Kontent keyin o'sib boradi (custom select, Alpine, grafik) — foydalanuvchi qimirlamaguncha qayta
    document.addEventListener("DOMContentLoaded", apply);
    window.addEventListener("load", apply);
    document.addEventListener("alpine:initialized", apply);

    // Forma natijasi xabari (.msg) tepada — skroll tiklangani uchun ko'rinmay qolsa, toast qilib ko'rsatamiz
    if (afterPost && main && target && target.main && target.main[1] > 40) {
      document.addEventListener("alpine:initialized", function () {
        var kinds = { error: "bad", warning: "warn", success: "ok", info: "ok" };
        main.querySelectorAll(".content > .msg").forEach(function (m) {
          if (m.getBoundingClientRect().bottom > main.getBoundingClientRect().top + 8) return;
          var kind = "ok";
          Object.keys(kinds).forEach(function (k) { if (m.classList.contains(k)) kind = kinds[k]; });
          if (window.toast) window.toast(m.textContent.trim(), kind);
        });
      });
    }

    // Server formani rad etsa (xato xabari bilan o'sha sahifaga qaytsa) — kiritilganlar qayta
    // to'ldiriladi: sotuvchi ism/telefon/summani qaytadan yozmasin. Parol, fayl, yashirin — yo'q.
    var SKIP = { password: 1, file: 1, hidden: 1, submit: 1, button: 1, reset: 1, image: 1 };
    function formKey(f) {
      var action = f.getAttribute("action") || "";
      var same = [].filter.call(document.forms, function (x) { return (x.getAttribute("action") || "") === action; });
      return action + "#" + same.indexOf(f);
    }
    // Alpine komponent holati bo'lgan yashirin maydon (sana tanlagich) — tiklanadi
    function isStateHidden(el) {
      return el.type === "hidden" && (el.hasAttribute(":value") || el.hasAttribute("x-bind:value"));
    }
    function skip(el) {
      return !el.name || el.name === "csrfmiddlewaretoken" || (SKIP[el.type] && !isStateHidden(el));
    }
    function formValues(f) {
      var out = {};
      [].forEach.call(f.elements, function (el) {
        if (skip(el) || el.disabled) return;
        if (el.type === "checkbox" || el.type === "radio") {
          out[el.name + "|" + el.value] = el.checked;
        } else if (el.value !== "") {
          out[el.name] = el.value;
        }
      });
      return out;
    }
    function refill() {
      var f = [].find.call(document.forms, function (x) { return formKey(x) === ret.form.key; });
      if (!f) return;
      var vals = ret.form.values;
      [].forEach.call(f.elements, function (el) {
        if (skip(el)) return;
        if (el.type === "checkbox" || el.type === "radio") {
          var k = el.name + "|" + el.value;
          if (k in vals && el.checked !== !!vals[k]) {
            el.checked = !!vals[k];
            el.dispatchEvent(new Event("change", { bubbles: true }));
          }
        } else if (el.name in vals) {
          if (isStateHidden(el)) {  // sana tanlagich: komponent holati orqali
            var host = el.closest("[x-data]");
            var data = host && window.Alpine && window.Alpine.$data(host);
            if (data && typeof data.setIso === "function") data.setIso(vals[el.name]);
            return;
          }
          el.value = vals[el.name];
          el.dispatchEvent(new Event("input", { bubbles: true }));
          el.dispatchEvent(new Event("change", { bubbles: true }));  // custom select yorlig'i
        }
      });
    }
    if (afterPost && ret && ret.form && document.querySelector(".content > .msg.error")) {
      // Alpine'dan KEYIN: aks holda Alpine boshlang'ich (bo'sh) qiymat bilan ustidan yozadi
      document.addEventListener("alpine:initialized", function () { setTimeout(refill, 0); });
    }

    window.addEventListener("pagehide", function () { sset("bn-pos:" + here, JSON.stringify(snapshot())); });
    function rememberForPost(form) {
      var data = { path: location.pathname, pos: snapshot(), t: Date.now() };
      if (form && form.elements) data.form = { key: formKey(form), values: formValues(form) };
      sset("bn-post-return", JSON.stringify(data));
    }
    window.__bnRememberScroll = rememberForPost;  // form.submit() (tasdiqlash oynasi) submit hodisasisiz
    document.addEventListener("submit", function (e) {
      var f = e.target;
      if (e.defaultPrevented || !f || (f.getAttribute("method") || "").toLowerCase() !== "post") return;
      if (f.hasAttribute("hx-post")) return;  // HTMX sahifani almashtirmaydi
      rememberForPost(f);
    });
  })();

  // ---- Tasdiqlash oynasi: <form data-confirm="Matn" data-confirm-ok="Ha, o'chirish"> ----
  // Brauzerning standart confirm() oynasi o'rniga bizning dizayndagi modal.
  function confirmModal(text, okLabel, danger) {
    return new Promise(function (resolve) {
      var bd = document.createElement("div");
      bd.className = "modal-backdrop";
      bd.innerHTML =
        '<div class="modal-card center" role="alertdialog" aria-modal="true">' +
        '<div class="card-title" style="margin:0 0 var(--sp-2)"></div>' +
        '<p class="muted" style="margin:0 0 var(--sp-4)">Bu amalni tasdiqlaysizmi?</p>' +
        '<div class="row gap-2" style="justify-content:center">' +
        '<button type="button" class="btn btn-ghost" data-act="no">Bekor</button>' +
        '<button type="button" class="btn ' + (danger ? "btn-danger" : "") + '" data-act="yes"></button>' +
        "</div></div>";
      bd.querySelector(".card-title").textContent = text;
      bd.querySelector('[data-act="yes"]').textContent = okLabel || "Ha";
      function done(v) {
        document.removeEventListener("keydown", onKey, true);
        bd.remove();
        resolve(v);
      }
      function onKey(e) { if (e.key === "Escape") { e.preventDefault(); done(false); } }
      bd.addEventListener("click", function (e) {
        var act = e.target.closest("[data-act]");
        if (act) done(act.dataset.act === "yes");
        else if (e.target === bd) done(false);
      });
      document.addEventListener("keydown", onKey, true);
      document.body.appendChild(bd);
      if (window.i18nApply) window.i18nApply(bd);
      bd.querySelector('[data-act="no"]').focus();
    });
  }
  window.confirmModal = confirmModal;

  // Xaridorga QR chek: sotuvchi ekranini xaridorga buradi, xaridor telefon kamerasi bilan skanerlaydi
  function showReceiptQR(d) {
    if (!d || !d.qr) return;
    var bd = document.createElement("div");
    bd.className = "modal-backdrop";
    bd.innerHTML =
      '<div class="modal-card center receipt-modal" role="dialog" aria-modal="true" aria-label="Xaridorga chek">' +
      '<div class="card-title" style="margin:0 0 var(--sp-1)">Xaridorga chek</div>' +
      '<div class="receipt-amt num" data-noloc></div>' +
      '<div class="receipt-qr"><img alt="Chek QR kodi" width="240" height="240"></div>' +
      '<p class="muted" style="margin:var(--sp-2) 0 var(--sp-4);font-size:var(--t--1)">' +
      "Xaridor telefon kamerasi bilan skanerlaydi: chekni ko'radi, summa noto'g'ri bo'lsa xabar beradi.</p>" +
      '<div class="receipt-code num" data-noloc></div>' +
      '<button type="button" class="btn btn-block" data-act="close">Yopish</button>' +
      "</div>";
    bd.querySelector("img").src = d.qr;
    bd.querySelector(".receipt-amt").textContent = (window.BN ? window.BN.fmt(d.total) : d.total) + " so'm";
    bd.querySelector(".receipt-code").textContent = d.url || "";
    function done() { document.removeEventListener("keydown", onKey, true); bd.remove(); }
    function onKey(e) { if (e.key === "Escape") { e.preventDefault(); done(); } }
    bd.addEventListener("click", function (e) {
      if (e.target === bd || e.target.closest('[data-act="close"]')) done();
    });
    document.addEventListener("keydown", onKey, true);
    document.body.appendChild(bd);
    if (window.i18nApply) window.i18nApply(bd);
    bd.querySelector('[data-act="close"]').focus();
  }
  window.showReceiptQR = showReceiptQR;
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[data-receipt-qr]");
    if (!b) return;
    showReceiptQR({ qr: b.dataset.receiptQr, url: b.dataset.receiptUrl, total: +b.dataset.receiptTotal });
  });
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!form.matches || !form.matches("form[data-confirm]") || form.__confirmed) return;
    e.preventDefault();
    var submitter = e.submitter;
    confirmModal(form.dataset.confirm, form.dataset.confirmOk, form.hasAttribute("data-danger"))
      .then(function (ok) {
        if (!ok) return;
        form.__confirmed = true;
        if (submitter && submitter.name) {
          // Bosilgan tugma qiymati (name/value) yo'qolmasin
          var h = document.createElement("input");
          h.type = "hidden"; h.name = submitter.name; h.value = submitter.value;
          form.appendChild(h);
        }
        if ((form.getAttribute("method") || "").toLowerCase() === "post" && window.__bnRememberScroll) {
          window.__bnRememberScroll(form);  // form.submit() submit hodisasini chiqarmaydi
        }
        form.submit();
      });
  }, true);

  // ---- Offline sotuv navbati (umumiy: tez sotuv + skaner) ----
  // Internet uzilsa sotuv localStorage'ga tushadi; har sahifa ochilganda va tarmoq
  // qaytganda yuboriladi. client_uid tufayli qayta yuborish dublikat yaratmaydi.
  // Sotuv HECH QACHON jimgina o'chirilmaydi — u real bo'lgan (yo'qolsa yashirilgan savdoga
  // aylanadi): sessiya tugasa (401/403) yoki boshqa do'konniki bo'lsa (409) navbatda qoladi,
  // boshqa rad javoblari "qabul qilinmadi" ro'yxatiga o'tib, qo'lda kiritish uchun ekranda turadi.
  window.saleQueue = {
    KEY: "saleQueue",
    REJ: "saleQueueRejected",
    _get: function (k) {
      try { return JSON.parse(localStorage.getItem(k) || "[]"); } catch (e) { return []; }
    },
    _set: function (k, v) {
      try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* to'la */ }
    },
    list: function () { return this._get(this.KEY); },
    rejected: function () { return this._get(this.REJ); },
    add: function (body) {
      body.offline = true;  // server haqiqiy vaqtiga (client_ts) yozadi
      body.shop_hint = window.BN_SHOP || null;
      var q = this.list(); q.push(body);
      this._set(this.KEY, q);
      return q.length;
    },
    uid: function () {
      return (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
        : (Date.now() + "-" + Math.random().toString(36).slice(2));
    },
    _running: null,
    sync: function () {
      // Bir vaqtda bitta yuborish: parallel chaqiruv o'sha jarayon natijasini kutadi
      if (!this._running) {
        var self = this;
        this._running = this._send().finally(function () { self._running = null; });
      }
      return this._running;
    },
    _send: async function () {
      var q = this.list();
      // Faqat sotuvchi sahifasida (kirish sahifasida yoki boshqa rolda yubormaymiz)
      if (!q.length || !navigator.onLine || !window.BN_SHOP) { this.renderRejected(); return q.length; }
      var rest = [], rej = this.rejected(), newRej = 0, auth = false, foreign = 0;
      var csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || "";
      for (var i = 0; i < q.length; i++) {
        var item = q[i];
        if (item.shop_hint && item.shop_hint !== window.BN_SHOP) { foreign++; rest.push(item); continue; }
        try {
          var r = await fetch("/api/sales/", { method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
            body: JSON.stringify(item) });
          if (r.ok) continue;
          if (r.status === 401 || r.status === 403) { auth = true; rest.push(item); continue; }
          if (r.status === 409) { foreign++; rest.push(item); continue; }
          if (r.status >= 400 && r.status < 500) {
            var detail = "";
            try { detail = (await r.json()).detail || ""; } catch (e) { /* matn emas */ }
            rej.push({ body: item, detail: String(detail).slice(0, 200), at: new Date().toISOString() });
            newRej++;
            continue;
          }
          rest.push(item);  // 5xx — keyinroq qayta
        } catch (e) { rest.push(item); }
      }
      this._set(this.KEY, rest);
      this._set(this.REJ, rej);
      var t = window.toast || function () {};
      if (auth) t("Qayta kiring — " + rest.length + " ta sotuv navbatda saqlanib turibdi", "warn");
      else if (newRej) t(newRej + " ta navbatdagi sotuv qabul qilinmadi — ro'yxatni ko'ring", "bad");
      else if (foreign && rest.length === foreign) t("Bu qurilmada boshqa sotuvchining " + foreign + " ta yuborilmagan sotuvi bor", "warn");
      else if (!rest.length) t("Navbatdagi sotuvlar yuborildi", "ok");
      this.renderRejected();
      return rest.length;
    },
    // Qabul qilinmagan oflayn sotuvlar — sotuvchi qo'lda qayta kiritguncha ekranda turadi
    renderRejected: function () {
      var old = document.getElementById("sq-rejected");
      var mine = function (x) { return !x.body.shop_hint || x.body.shop_hint === window.BN_SHOP; };
      var rej = this.rejected().filter(mine);
      if (!rej.length || !window.BN_SHOP) { if (old) old.remove(); return; }
      var box = old || document.createElement("div");
      box.id = "sq-rejected";
      box.className = "sq-rejected card";
      box.setAttribute("role", "alert");
      var fmt = function (n) { return window.BN ? window.BN.fmt(Math.round(n)) : Math.round(n); };
      var two = function (n) { return ("0" + n).slice(-2); };
      box.innerHTML = "";
      var title = document.createElement("div");
      title.className = "card-title";
      title.textContent = "Oflayn sotuvlar qabul qilinmadi";
      var hint = document.createElement("p");
      hint.className = "muted";
      hint.textContent = "Bu sotuvlarni qo'lda qayta kiriting (sabab yonida).";
      var ul = document.createElement("ul");
      rej.forEach(function (x) {
        var b = x.body;
        var sum = (b.items || []).reduce(function (s, i) { return s + (+i.qty || 0) * (+i.unit_price || 0); }, 0)
          - (+b.discount || 0) - (+b.rounding || 0);
        var when = b.client_ts ? new Date(b.client_ts) : null;
        var li = document.createElement("li");
        var amt = document.createElement("b");
        amt.className = "num";
        amt.textContent = fmt(sum) + " so'm";
        li.appendChild(amt);
        if (when) {
          var ws = document.createElement("span");
          ws.className = "muted num";
          ws.textContent = " " + two(when.getDate()) + "." + two(when.getMonth() + 1) + " "
            + two(when.getHours()) + ":" + two(when.getMinutes());
          li.appendChild(ws);
        }
        if (x.detail) {  // server matni — textContent (XSS bo'lmasin)
          var why = document.createElement("span");
          why.textContent = " — " + x.detail;
          li.appendChild(why);
        }
        ul.appendChild(li);
      });
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-ghost";
      btn.textContent = "Qayta kiritdim — ro'yxatni tozalash";
      var self = this;
      btn.onclick = function () {
        self._set(self.REJ, self.rejected().filter(function (x) { return !mine(x); }));
        box.remove();
      };
      box.append(title, hint, ul, btn);
      if (!old) document.body.appendChild(box);
    },
  };
  // Kassa / kun yakunini yopishdan oldin: yuborilmagan oflayn sotuv bo'lsa to'xtatamiz —
  // aks holda kutilgan naqd ulardan kam chiqib, sotuvchiga soxta "kassa ortiqchasi" signali ketardi
  document.addEventListener("submit", function (e) {
    var f = e.target;
    if (!f.hasAttribute || !f.hasAttribute("data-queue-guard")) return;
    var own = window.saleQueue.list().filter(function (x) {
      return !x.shop_hint || x.shop_hint === window.BN_SHOP;
    }).length;
    if (!own) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    window.toast && window.toast(own + " ta sotuv hali yuborilmagan — internet ulanishini kuting, keyin yoping", "warn");
    window.saleQueue.sync();
  }, true);

  // Navbatda sotuv qolgan bo'lsa — istalgan sahifa ochilganda / tarmoq qaytganda yuboriladi
  document.addEventListener("DOMContentLoaded", function () {
    if (window.saleQueue.list().length) window.saleQueue.sync();
    else window.saleQueue.renderRejected();
  });
  window.addEventListener("online", function () { window.saleQueue.sync(); });

  // ---- Raqamlar 0 dan sanalib chiqadi (.count-up) — dashboard "jonli" ko'rinadi ----
  function countUp(el) {
    var node = null;
    for (var i = 0; i < el.childNodes.length; i++) {
      var n = el.childNodes[i];
      if (n.nodeType === 3 && /\d/.test(n.textContent)) { node = n; break; }
    }
    if (!node) return;
    var orig = node.textContent;
    var target = parseInt(orig.replace(/\D/g, ""), 10);
    if (!target || target > 2000000000) return;
    var pct = orig.indexOf("%") >= 0 ? "%" : "";
    var trail = /\s$/.test(orig) ? " " : "";
    var fmt = function (v) { return window.BN ? window.BN.fmt(v) : String(v); };
    var dur = 700, t0 = performance.now();
    function step(now) {
      var p = Math.min(1, (now - t0) / dur);
      var val = Math.floor((1 - Math.pow(1 - p, 3)) * target);
      node.textContent = fmt(val) + pct + trail;
      if (p < 1) requestAnimationFrame(step);
      else node.textContent = fmt(target) + pct + trail;
    }
    requestAnimationFrame(step);
  }
  document.addEventListener("DOMContentLoaded", function () {
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion:reduce)").matches;
    if (reduce || window.__bnQuiet) return;
    document.querySelectorAll(".count-up").forEach(countUp);
  });

  // ---- Barkod skaner (kamera) — ZXing, hamma brauzerda ishlaydi ----
  window.openBarcodeScanner = function (onDetect) {
    if (!window.ZXing) {
      window.toast && window.toast("Skaner yuklanmadi — qo'lda kiriting", "bad");
      return;
    }
    const ov = document.createElement("div");
    ov.className = "scanner-overlay";
    ov.innerHTML =
      '<div class="scanner-box">' +
      '<video class="scanner-video" playsinline muted></video>' +
      '<div class="scanner-frame"></div>' +
      '<div class="scanner-hint">Barkodni ramka ichiga tuting</div>' +
      '<button type="button" class="btn btn-danger scanner-close">Yopish</button>' +
      "</div>";
    document.body.appendChild(ov);
    const video = ov.querySelector("video");
    const reader = new window.ZXing.BrowserMultiFormatReader();
    let done = false;
    function close() {
      if (done) return;
      done = true;
      try { reader.reset(); } catch (e) {}
      ov.remove();
    }
    ov.querySelector(".scanner-close").addEventListener("click", close);
    ov.addEventListener("click", (e) => { if (e.target === ov) close(); });
    reader
      .decodeFromConstraints({ video: { facingMode: "environment" } }, video, (result) => {
        if (result && !done) {
          const val = result.getText();
          close();
          try { navigator.vibrate && navigator.vibrate(80); } catch (e) {}
          onDetect(val);
        }
      })
      .catch(() => {
        window.toast && window.toast("Kamera ochilmadi — ruxsat bering yoki qo'lda kiriting", "bad");
        close();
      });
  };

  // ---- Custom fayl tanlash: tanlangan fayl nomini ko'rsatadi ----
  document.addEventListener("change", (e) => {
    const inp = e.target;
    if (!inp.matches || !inp.matches('.file-drop input[type="file"]')) return;
    const drop = inp.closest(".file-drop");
    const nameEl = drop && drop.querySelector(".file-name");
    if (nameEl) {
      const f = inp.files && inp.files[0];
      nameEl.textContent = f ? f.name : "Fayl tanlanmagan";
      drop.classList.toggle("has-file", !!f);
    }
  });

  document.addEventListener("alpine:init", () => {
    // ---- Custom sana maydoni (o'zbekcha kalendar, hidden inputga yozadi) ----
    // future=true: bo'sh boshlanadi (jimgina "bugun" bo'lib qolmasin) va o'tgan kun tanlanmaydi
    Alpine.data("dateField", (initialIso = "", future = false) => ({
      open: false,
      future: future,
      months: calMonths(),
      wd: calWd(),
      value: initialIso ? new Date(initialIso + "T00:00:00") : (future ? null : new Date()),
      view: initialIso ? new Date(initialIso + "T00:00:00") : new Date(),
      get iso() {
        const d = this.value;
        if (!d) return "";
        return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
          d.getDate()
        ).padStart(2, "0")}`;
      },
      get display() {
        const d = this.value;
        if (!d) return "Sanani tanlang";
        return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(
          2,
          "0"
        )}.${d.getFullYear()}`;
      },
      isPast(d) {
        if (!this.future) return false;
        const t = new Date(); t.setHours(0, 0, 0, 0);
        return d < t;
      },
      addDays(n) {
        const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() + n);
        this.value = d; this.view = new Date(d); this.open = false;
        this._fire();
      },
      // Tashqaridan qiymat berish (server xatosidan keyin forma qayta to'ldirilganda)
      setIso(s) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(String(s || ""))) return;
        const d = new Date(s + "T00:00:00");
        if (isNaN(d)) return;
        this.value = d; this.view = new Date(d);
        this._fire();
      },
      daysFromToday(n) {
        if (!this.value) return false;
        const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() + n);
        return this.isoOf(d) === this.iso;
      },
      get title() {
        return `${this.months[this.view.getMonth()]} ${this.view.getFullYear()}`;
      },
      get days() {
        const y = this.view.getFullYear();
        const m = this.view.getMonth();
        const lead = (new Date(y, m, 1).getDay() + 6) % 7;
        const out = [];
        for (let i = 0; i < lead; i++) out.push({ d: new Date(y, m, -(lead - 1 - i)), out: true });
        const dim = new Date(y, m + 1, 0).getDate();
        for (let i = 1; i <= dim; i++) out.push({ d: new Date(y, m, i), out: false });
        while (out.length % 7) {
          const last = out[out.length - 1].d;
          out.push({ d: new Date(last.getFullYear(), last.getMonth(), last.getDate() + 1), out: true });
        }
        return out;
      },
      prev() { this.view = new Date(this.view.getFullYear(), this.view.getMonth() - 1, 1); },
      next() { this.view = new Date(this.view.getFullYear(), this.view.getMonth() + 1, 1); },
      prevYear() { this.view = new Date(this.view.getFullYear() - 1, this.view.getMonth(), 1); },
      nextYear() { this.view = new Date(this.view.getFullYear() + 1, this.view.getMonth(), 1); },
      isoOf(d) {
        return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
          d.getDate()
        ).padStart(2, "0")}`;
      },
      isSel(d) { return this.isoOf(d) === this.iso; },
      isToday(d) { return this.isoOf(d) === this.isoOf(new Date()); },
      pick(d) { if (this.isPast(d)) return; this.value = d; this.open = false; this._fire(); },
      _fire() {
        // Majburiy maydon xatosi (qizil) sana tanlangach darhol yo'qolsin
        this.$nextTick(() => {
          const h = this.$root.querySelector('input[type="hidden"]');
          if (h) h.dispatchEvent(new Event("change", { bubbles: true }));
        });
      },
      today() { this.value = new Date(); this.view = new Date(); this.open = false; },
    }));

    // ---- Tema boshqaruvi (light/dark/tizim) ----
    Alpine.data("themeCtl", () => ({
      theme: document.documentElement.getAttribute("data-theme") || "",
      set(v) {
        this.theme = v;
        if (v) document.documentElement.setAttribute("data-theme", v);
        else document.documentElement.removeAttribute("data-theme");
        // Serverga saqlaymiz (cookie ham o'rnatiladi)
        const fd = new FormData(); fd.append("theme", v);
        fd.append("csrfmiddlewaretoken", getCookie("csrftoken"));
        fetch("/prefs/theme/", { method: "POST", body: fd,
          headers: { "HX-Request": "true" } }).catch(() => {});
      },
    }));

    // ---- Qidiruvli select ----
    Alpine.data("selectBox", (opts = [], selected = "", name = "") => ({
      open: false, q: "", value: selected, name,
      options: opts, // [{value,label}]
      get filtered() {
        const q = this.q.toLowerCase();
        return this.options.filter(o => o.label.toLowerCase().includes(q));
      },
      get label() {
        const o = this.options.find(o => String(o.value) === String(this.value));
        return o ? o.label : "Tanlang";
      },
      pick(v) { this.value = v; this.open = false; this.q = ""; },
      toggle() { this.open = !this.open; if (this.open) this.$nextTick(() => this.$refs.search?.focus()); },
    }));

    // ---- Kalendar (bitta yoki diapazon), o'zbekcha oylar ----
    Alpine.data("datePicker", (mode = "single") => ({
      open: false, mode,
      view: new Date(),
      start: null, end: null,
      months: calMonths(), wd: calWd(),
      get title() { return `${this.months[this.view.getMonth()]} ${this.view.getFullYear()}`; },
      get days() {
        const y = this.view.getFullYear(), m = this.view.getMonth();
        const first = new Date(y, m, 1);
        let lead = (first.getDay() + 6) % 7; // Dushanba = 0
        const out = [];
        for (let i = 0; i < lead; i++) {
          const d = new Date(y, m, -(lead - 1 - i));
          out.push({ d, out: true });
        }
        const dim = new Date(y, m + 1, 0).getDate();
        for (let i = 1; i <= dim; i++) out.push({ d: new Date(y, m, i), out: false });
        while (out.length % 7) { const last = out[out.length-1].d;
          out.push({ d: new Date(last.getFullYear(), last.getMonth(), last.getDate()+1), out:true }); }
        return out;
      },
      prev() { this.view = new Date(this.view.getFullYear(), this.view.getMonth() - 1, 1); },
      next() { this.view = new Date(this.view.getFullYear(), this.view.getMonth() + 1, 1); },
      prevYear() { this.view = new Date(this.view.getFullYear() - 1, this.view.getMonth(), 1); },
      nextYear() { this.view = new Date(this.view.getFullYear() + 1, this.view.getMonth(), 1); },
      iso(d) { return d.toISOString().slice(0, 10); },
      isToday(d) { return this.iso(d) === this.iso(new Date()); },
      isSel(d) { const s = this.iso(d);
        return (this.start && s === this.iso(this.start)) || (this.end && s === this.iso(this.end)); },
      inRange(d) { return this.mode === "range" && this.start && this.end &&
        d > this.start && d < this.end; },
      choose(day) {
        const d = day.d;
        if (this.mode === "single") { this.start = d; this.open = false; return; }
        if (!this.start || (this.start && this.end)) { this.start = d; this.end = null; }
        else if (d < this.start) { this.end = this.start; this.start = d; }
        else { this.end = d; }
      },
      get display() {
        if (this.mode === "single") return this.start ? this.fmtD(this.start) : "Sanani tanlang";
        if (this.start && this.end) return `${this.fmtD(this.start)} — ${this.fmtD(this.end)}`;
        if (this.start) return `${this.fmtD(this.start)} — ...`;
        return "Davrni tanlang";
      },
      fmtD(d) { return `${String(d.getDate()).padStart(2,"0")}.${String(d.getMonth()+1).padStart(2,"0")}.${d.getFullYear()}`; },
    }));

    // ---- Summa maydoni (1 234 567) ----
    Alpine.data("amount", (initial = 0) => ({
      raw: initial || 0,
      get shown() { return fmt(this.raw); },
      set shown(v) { this.raw = unfmt(v); },
    }));

    // ---- Toast do'koni ----
    Alpine.store("toasts", {
      items: [],
      push(msg, kind = "ok") {
        const id = Date.now() + Math.random();
        this.items.push({ id, msg, kind });
        setTimeout(() => this.remove(id), 3500);
      },
      remove(id) { this.items = this.items.filter(t => t.id !== id); },
    });
    window.toast = (m, k) => Alpine.store("toasts").push(m, k);
  });
})();
