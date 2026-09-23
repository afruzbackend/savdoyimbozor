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

  // ---- Custom fayl tanlash: tanlanган fayl nomini ko'rsatadi ----
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
    Alpine.data("dateField", (initialIso = "") => ({
      open: false,
      months: calMonths(),
      wd: calWd(),
      value: initialIso ? new Date(initialIso + "T00:00:00") : new Date(),
      view: initialIso ? new Date(initialIso + "T00:00:00") : new Date(),
      get iso() {
        const d = this.value;
        return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
          d.getDate()
        ).padStart(2, "0")}`;
      },
      get display() {
        const d = this.value;
        return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(
          2,
          "0"
        )}.${d.getFullYear()}`;
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
      pick(d) { this.value = d; this.open = false; },
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
