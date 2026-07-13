(() => {
  const protocol = window.location.protocol === "https:" ? "https:" : "http:";
  const hostname = window.location.hostname || "localhost";

  window.ADNOVA_CONFIG = {
    API_BASE_URL: `${protocol}//${hostname}:8000`,
    ...(window.ADNOVA_CONFIG || {}),
  };
})();
