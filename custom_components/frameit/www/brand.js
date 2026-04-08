// Redirect HA brands CDN requests for the frameit domain to the locally
// registered icon, since private custom integrations are not in the brands repo.
(function () {
  var ICON = "/frameit_www/icon.svg";

  function isFrameItBrand(url) {
    return (
      typeof url === "string" &&
      url.includes("brands.home-assistant.io") &&
      url.includes("/frameit/")
    );
  }

  // Override HTMLImageElement.prototype.src so Lit property bindings
  // (img.src = brandsUrl(...)) are intercepted before the request fires.
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

  // Also cover setAttribute for any code paths that set src as an attribute.
  var origSetAttr = Element.prototype.setAttribute;
  Element.prototype.setAttribute = function (name, value) {
    if (this instanceof HTMLImageElement && name === "src" && isFrameItBrand(value)) {
      value = ICON;
    }
    return origSetAttr.call(this, name, value);
  };
})();
