/* Alpine.js komponentlari — custom, ARIA + klaviatura bilan. Brauzer default'lari yo'q. */
(function () {
  const UZ_MONTHS = ["Yanvar","Fevral","Mart","Aprel","May","Iyun","Iyul",
    "Avgust","Sentabr","Oktabr","Noyabr","Dekabr"];
  const UZ_WD = ["Du","Se","Cho","Pa","Ju","Sh","Ya"]; // Dushanbadan

  // Summani "1 234 567" ko'rinishida formatlash
  function fmt(n) {
    n = String(n).replace(/\D/g, "");
    return n.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  }
  function unfmt(s) { return parseInt(String(s).replace(/\D/g, ""), 10) || 0; }
  window.BN = { fmt, unfmt, UZ_MONTHS, UZ_WD };

  function getCookie(name) {
    const m = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return m ? m.pop() : "";
  }

  document.addEventListener("alpine:init", () => {
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
      months: UZ_MONTHS, wd: UZ_WD,
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
