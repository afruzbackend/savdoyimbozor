/* O'zbek lotin → kirill avtomatik transliteratsiya (UI tili).
   Lotin — manba; kirill deterministik hosil qilinadi (ikki katalog saqlanmaydi).
   Rus tili gettext bilan alohida qo'shiladi (muhitda gettext bo'lganda).

   Ishlashi: cookie `uilang` = "" (lotin) yoki "cyrl". "cyrl" bo'lsa sahifa
   matn tugunlari transliteratsiya qilinadi. [data-noloc], input, script, code
   va raqamlar tegilmaydi. HTMX yangilanishida qayta qo'llanadi. */
(function () {
  // Digraflar avval (uzunroq mos kelish oldin)
  const DIGRAPHS = [
    ["o'", "ў"], ["g'", "ғ"], ["sh", "ш"], ["ch", "ч"], ["yo", "ё"],
    ["yu", "ю"], ["ya", "я"], ["ts", "ц"],
  ];
  const SINGLE = {
    a: "а", b: "б", d: "д", e: "е", f: "ф", g: "г", h: "ҳ", i: "и", j: "ж",
    k: "к", l: "л", m: "м", n: "н", o: "о", p: "п", q: "қ", r: "р", s: "с",
    t: "т", u: "у", v: "в", x: "х", y: "й", z: "з", c: "к", "'": "ъ", "`": "ъ",
  };

  function isUpper(ch) { return ch !== ch.toLowerCase() && ch === ch.toUpperCase(); }
  function applyCase(src, dst) {
    return isUpper(src[0]) ? dst.charAt(0).toUpperCase() + dst.slice(1) : dst;
  }

  function translitWord(w) {
    let out = "";
    let i = 0;
    while (i < w.length) {
      let matched = false;
      const two = w.substr(i, 2).toLowerCase();
      for (const [lat, cyr] of DIGRAPHS) {
        if (two === lat) {
          out += applyCase(w.substr(i, 2), cyr);
          i += 2; matched = true; break;
        }
      }
      if (matched) continue;
      const ch = w[i];
      const low = ch.toLowerCase();
      if (SINGLE[low] !== undefined) {
        out += isUpper(ch) ? SINGLE[low].toUpperCase() : SINGLE[low];
      } else {
        out += ch; // raqam, tinish belgisi, boshqa
      }
      i += 1;
    }
    return out;
  }

  function translit(text) {
    // So'zlarni ajratmasdan belgima-belgi (digraf oynasi bilan) ishlaymiz
    return translitWord(text);
  }

  const SKIP_TAGS = new Set(["SCRIPT", "STYLE", "CODE", "PRE", "TEXTAREA", "INPUT"]);

  // Rus tili lug'ati (uz-lotin → rus). Faqat interfeys matnlari; ma'lumot (nom/raqam) qolaveradi.
  const RU = window.RU_DICT || {};
  const RU_FRAG = window.RU_FRAGMENTS || [];
  function ruText(text) {
    const key = text.trim();
    if (!key) return text;
    const t = RU[key];
    if (t !== undefined) return text.replace(key, t); // aniq moslik (bo'sh joy saqlanadi)
    // Aniq moslik yo'q — dinamik bo'laklarni almashtiramiz (signal sabablari)
    let out = text;
    for (const [a, b] of RU_FRAG) {
      if (out.includes(a)) out = out.split(a).join(b);
    }
    return out;
  }

  // Tarjima qilinadigan atributlar (placeholder, tooltip, aria)
  const ATTRS = ["placeholder", "title", "aria-label"];
  function transformAttrs(el, transform) {
    if (!el.getAttribute) return;
    for (const a of ATTRS) {
      const v = el.getAttribute(a);
      if (v && v.trim()) el.setAttribute(a, transform(v));
    }
  }

  // Grafik (canvas) matnlari DOM tugunlari emas — ular shu funksiya bilan
  // joriy tilga o'giriladi. Chart.js skriptlari label'ni shu orqali beradi.
  window.locText = function (s) {
    const lang = getCookie("uilang");
    if (lang === "cyrl") return translit(s);
    if (lang === "ru") return ruText(s);
    return s;
  };

  function walk(node, transform) {
    if (node.nodeType === Node.TEXT_NODE) {
      if (node.nodeValue && node.nodeValue.trim()) {
        node.nodeValue = transform(node.nodeValue);
      }
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    if (node.hasAttribute && node.hasAttribute("data-noloc")) return;
    transformAttrs(node, transform); // input'da ham atribut tarjima qilinadi
    if (SKIP_TAGS.has(node.tagName)) return; // ichki matn (input qiymati) tegilmaydi
    for (const child of node.childNodes) walk(child, transform);
  }

  function getCookie(n) {
    const m = document.cookie.match("(^|;)\\s*" + n + "\\s*=\\s*([^;]+)");
    return m ? m.pop() : "";
  }

  window.setUiLang = function (v) {
    document.cookie = "uilang=" + v + ";path=/;max-age=" + 60 * 60 * 24 * 365 + ";samesite=Lax";
    // Tugma ustidagi doppi sweep ko'rinib bo'lgach yangilaymiz (milliy o'tish)
    setTimeout(function () { location.reload(); }, 440);
  };

  function run() {
    const lang = getCookie("uilang");
    let transform = null;
    if (lang === "cyrl") {
      transform = translit;
      document.documentElement.setAttribute("lang", "uz-Cyrl");
    } else if (lang === "ru") {
      transform = ruText;
      document.documentElement.setAttribute("lang", "ru");
    }
    if (!transform) return;
    walk(document.body, transform);
    // HTMX bilan kelgan yangi bo'laklarni ham
    document.body.addEventListener("htmx:afterSwap", (e) => walk(e.target, transform));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
