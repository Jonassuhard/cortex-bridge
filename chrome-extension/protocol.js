export const EXTENSION_PROTOCOL_VERSION = 3;
export const SESSION_RECEIPT_CAPABILITY = "session_quiescence_receipt_v1";

export function createPairMessage(token, { workerEpoch, capabilities } = {}) {
  return {
    type: "pair",
    token,
    protocol_version: EXTENSION_PROTOCOL_VERSION,
    worker_epoch: workerEpoch,
    capabilities,
  };
}

export class ExtensionCommandError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "ExtensionCommandError";
    this.code = code;
  }
}

export function commandError(error) {
  return {
    code: error?.code || "EXTENSION_COMMAND_FAILED",
    message: error instanceof Error ? error.message : "Chrome extension command failed",
  };
}

export function isChatGPTUrl(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" && parsed.hostname === "chatgpt.com";
  } catch {
    return false;
  }
}
