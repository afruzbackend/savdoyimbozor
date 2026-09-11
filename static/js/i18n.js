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

  function walk(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      if (node.nodeValue && node.nodeValue.trim()) {
        node.nodeValue = translit(node.nodeValue);
      }
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    if (SKIP_TAGS.has(node.tagName)) return;
    if (node.hasAttribute && node.hasAttribute("data-noloc")) return;
    for (const child of node.childNodes) walk(child);
  }

  function getCookie(n) {
    const m = document.cookie.match("(^|;)\\s*" + n + "\\s*=\\s*([^;]+)");
    return m ? m.pop() : "";
  }

  window.setUiLang = function (v) {
    document.cookie = "uilang=" + v + ";path=/;max-age=" + 60 * 60 * 24 * 365 + ";samesite=Lax";
    location.reload();
  };

  function run() {
    if (getCookie("uilang") !== "cyrl") return;
    document.documentElement.setAttribute("lang", "uz-Cyrl");
    walk(document.body);
    // HTMX bilan kelgan yangi bo'laklarni ham
    document.body.addEventListener("htmx:afterSwap", (e) => walk(e.target));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
