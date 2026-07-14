(() => {
  const protocol = window.location.protocol === "https:" ? "https:" : "http:";
  const hostname = window.location.hostname || "localhost";
  const apiBaseUrl =
    protocol === "https:"
      ? window.location.origin
      : `${protocol}//${hostname}:8000`;

  window.ADNOVA_CONFIG = {
    API_BASE_URL: apiBaseUrl,
    ...(window.ADNOVA_CONFIG || {}),
  };
})();
