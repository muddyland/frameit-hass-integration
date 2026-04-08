// Serve the local FrameIT icon wherever HA's frontend would request it from
// the brands CDN — works for both the integrations panel and HACS.
(function () {
  var ICON = "/frameit_www/icon.png";

  function isFrameItBrand(url) {
    return (
      typeof url === "string" &&
      url.includes("frameit") &&
      (url.includes("brands.home-assistant.io") || url.includes("/api/brands/"))
    );
  }

  // ── Proactive: intercept img.src property assignments ──────────────
  // Lit sets img.src via the property setter, so we patch the prototype
  // before any integration-icon components are rendered.
  var desc = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, "src");
  if (desc && desc.set) {
    Object.defineProperty(HTMLImageElement.prototype, "src", {
      configurable: true,
      enumerable: desc.enumerable,
      get: desc.get,
      set: function (v) {
        desc.set.call(this, isFrameItBrand(v) ? ICON : v);
      },
    });
  }

  // Cover setAttribute too, for any code path that uses it.
  var origSetAttr = Element.prototype.setAttribute;
  Element.prototype.setAttribute = function (name, value) {
    if (this instanceof HTMLImageElement && name === "src" && isFrameItBrand(value)) {
      value = ICON;
    }
    return origSetAttr.call(this, name, value);
  };

  // ── Reactive fallback: replace on 404 / load-error ─────────────────
  // Catches cases where the img was already in the DOM before this script
  // ran, or when the brands CDN returns a 404 for an unknown domain.
  document.addEventListener(
    "error",
    function (e) {
      var t = e.target;
      if (
        t instanceof HTMLImageElement &&
        !t.dataset.frameitFixed &&
        isFrameItBrand(t.getAttribute("src") || t.src || "")
      ) {
        t.dataset.frameitFixed = "1";
        t.src = ICON;
      }
    },
    true // capture phase — fires before default handling
  );
})();
