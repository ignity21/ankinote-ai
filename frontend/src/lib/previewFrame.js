// Runs inside the card preview's sandboxed iframe (inlined with the page's
// CSP nonce; see CardPreview.svelte). The parent sends the card HTML by
// message, so editing a field updates the card in place instead of
// reloading the frame. Reports the frame's height, plays Anki replay
// buttons, and, when the page asks for MathJax, typesets the card the way
// Anki does (\( \) and \[ \]) and reports the formulas that didn't parse.
(() => {
  const root = document.documentElement;
  const doc = root.dataset.doc;
  const mathjax = root.dataset.mathjax;
  const nonce = document.currentScript?.nonce ?? "";
  const qa = document.getElementById("qa");
  const post = (data) => parent.postMessage({ ...data, doc }, "*");

  new ResizeObserver(() =>
    post({ height: Math.ceil(document.body.getBoundingClientRect().height) }),
  ).observe(document.body);

  document.addEventListener("click", (event) => {
    const button = event.target.closest(".replay-button[data-src]");
    if (!button) return;
    event.preventDefault();
    new Audio(button.dataset.src).play();
  });

  /** Formulas that failed in the current typeset: their TeX and why. */
  let errors = [];
  let typesetting = Promise.resolve();

  /**
   * A formula whose braces don't balance is never found (MathJax looks for
   * its end outside braces), so it shows as source and reports nothing.
   * Whatever opening delimiter is left in the text is one of those; its
   * `message` is empty and the app words it.
   */
  function unclosed() {
    const found = [];
    const walker = document.createTreeWalker(qa, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (node.parentElement?.closest("mjx-container")) continue;
      const text = node.nodeValue ?? "";
      const at = text.search(/\\[([]/);
      if (at >= 0) found.push({ tex: text.slice(at, at + 80), message: "" });
    }
    return found;
  }

  function show(content) {
    document.body.className = content.cls;
    qa.innerHTML = content.html;
    const mj = window.MathJax;
    if (!mj || typeof mj.typesetPromise !== "function") return;
    // MathJax typesets one call at a time.
    typesetting = typesetting
      .then(() => {
        errors = [];
        mj.typesetClear();
        return mj.typesetPromise([qa]);
      })
      .then(
        () => post({ math: [...errors, ...unclosed()] }),
        (error) => post({ math: [{ tex: "", message: String(error?.message ?? error) }] }),
      );
  }

  addEventListener("message", (event) => {
    if (event.source !== parent) return;
    const content = event.data?.ankinotePreview;
    if (content) show(content);
  });

  const ready = () => post({ ready: true });
  if (!mathjax) {
    ready();
    return;
  }

  // The sandbox has no storage; MathJax's menu settings look for some.
  try {
    void window.localStorage;
  } catch {
    const none = { getItem: () => null, setItem() {}, removeItem() {} };
    Object.defineProperty(window, "localStorage", { value: none });
  }

  window.MathJax = {
    tex: {
      // The full build turns these on: they show a broken formula as its
      // source, or an unknown command in red, and never report either.
      packages: { "[-]": ["noerrors", "noundefined"] },
      inlineMath: [["\\(", "\\)"]],
      displayMath: [["\\[", "\\]"]],
      processEscapes: false,
      processEnvironments: false,
      processRefs: false,
      formatError(jax, error) {
        errors.push({ tex: jax.latex ?? "", message: error.message });
        return jax.formatError(error);
      },
    },
    svg: { fontCache: "local" },
    options: { enableMenu: false },
    startup: {
      typeset: false,
      pageReady: () => {
        ready();
        return Promise.resolve();
      },
    },
  };
  const script = document.createElement("script");
  script.nonce = nonce;
  script.src = mathjax;
  // Without MathJax the card still shows, formulas as their source.
  script.onerror = ready;
  document.head.append(script);
})();
