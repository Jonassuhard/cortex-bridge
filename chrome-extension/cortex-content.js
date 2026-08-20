(() => {
  const TOKEN_PATTERN = /^[A-Za-z0-9_-]{43,256}$/;

  window.addEventListener("message", (event) => {
    if (
      event.source !== window
      || event.origin !== window.location.origin
      || event.data?.source !== "cortex-bridge-ui"
      || event.data?.type !== "CORTEX_PAIR_EXTENSION"
      || !TOKEN_PATTERN.test(event.data?.token || "")
    ) {
      return;
    }
    chrome.runtime.sendMessage(
      {
        source: "cortex-bridge-page",
        type: "cortex.pair",
        token: event.data.token,
      },
      (response) => {
        window.postMessage(
          {
            source: "cortex-bridge-extension",
            type: "CORTEX_PAIR_EXTENSION_RESULT",
            ok: Boolean(response?.ok),
            state: response?.state || "unavailable",
          },
          window.location.origin,
        );
      },
    );
  });
})();
