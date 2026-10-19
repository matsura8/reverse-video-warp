const HOST_NAME = "com.maxpowerit.reversewarp";
type BackgroundMessage =
  | { type: "reversewarp-start" }
  | { type: "reversewarp-process-frame"; frame: number[] }
  | { type: "reversewarp-request-tab-capture"; rect: DOMRectInit; viewportWidth: number; viewportHeight: number }
  | { type: "reversewarp-request-display-capture"; rect: DOMRectInit; viewportWidth: number; viewportHeight: number }
  | { type: "reversewarp-start-offscreen"; streamId: string; tabId: number; rect: DOMRectInit; viewportWidth: number; viewportHeight: number }
  | { type: "reversewarp-render-frame"; tabId?: number; frame: number[]; applied: boolean; probability: number }
  | { type: "reversewarp-stop" };
type Session = { endpoint: string; token: string };

let nativePort: chrome.runtime.Port | null = null;
let session: Session | null = null;
const pendingNative: Array<(value: unknown) => void> = [];

function connectNative(): chrome.runtime.Port {
  if (nativePort) return nativePort;
  nativePort = chrome.runtime.connectNative(HOST_NAME);
  nativePort.onMessage.addListener((message: unknown) => pendingNative.shift()?.(message));
  nativePort.onDisconnect.addListener(() => {
    nativePort = null;
    session = null;
  });
  return nativePort;
}

function nativeRequest(message: object): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const port = connectNative();
    const timeout = setTimeout(() => reject(new Error("native host timed out")), 15_000);
    pendingNative.push((value) => {
      clearTimeout(timeout);
      resolve(value);
    });
    port.postMessage(message);
  });
}

async function ensureSession(): Promise<Session> {
  if (session) return session;
  const response = (await nativeRequest({ type: "startSession" })) as {
    ok?: boolean;
    endpoint?: string;
    token?: string;
  };
  if (!response.ok || !response.endpoint || !response.token) {
    throw new Error("native host did not create a session");
  }
  session = { endpoint: response.endpoint, token: response.token };
  return session;
}

chrome.action.onClicked.addListener(async (tab) => {
  if (!tab.id) return;
  try {
    await ensureSession();
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] });
    await chrome.tabs.sendMessage(tab.id, { type: "reversewarp-start" } satisfies BackgroundMessage);
  } catch (error) {
    console.error("ReverseWarp could not start", error);
  }
});

chrome.runtime.onMessage.addListener((message: BackgroundMessage, _sender, sendResponse) => {
  if (message.type === "reversewarp-render-frame") {
    const tabId = _sender.tab?.id ?? message.tabId;
    if (tabId) void chrome.tabs.sendMessage(tabId, message);
    return false;
  }
  if (message.type === "reversewarp-process-frame") {
    void (async () => {
      try {
        const active = await ensureSession();
        const response = await fetch(`${active.endpoint}/v1/frame`, {
          method: "POST",
          headers: { Authorization: `Bearer ${active.token}`, "Content-Type": "image/jpeg" },
          body: new Uint8Array(message.frame),
        });
        if (!response.ok) throw new Error(`frame service returned ${response.status}`);
        const bytes = Array.from(new Uint8Array(await response.arrayBuffer()));
        sendResponse({
          ok: true,
          frame: bytes,
          applied: response.headers.get("x-reversewarp-applied") === "true",
          faceDetected: response.headers.get("x-reversewarp-face-detected") === "true",
          probability: Number(response.headers.get("x-reversewarp-probability") ?? 0),
        });
      } catch (error) {
        sendResponse({ ok: false, error: String(error) });
      }
    })();
    return true;
  }
  if (message.type === "reversewarp-request-tab-capture") {
    void (async () => {
      try {
        const tabId = _sender.tab?.id;
        if (!tabId || !chrome.offscreen || !chrome.tabCapture) throw new Error("tab capture is unavailable");
        const contexts = await chrome.runtime.getContexts({ contextTypes: [chrome.runtime.ContextType.OFFSCREEN_DOCUMENT] });
        if (contexts.length === 0) {
          await chrome.offscreen.createDocument({
            url: "offscreen.html",
            reasons: [chrome.offscreen.Reason.USER_MEDIA],
            justification: "Capture the user-selected tab for local ReverseWarp processing",
          });
        }
        const streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tabId });
        await chrome.runtime.sendMessage({
          type: "reversewarp-start-offscreen", streamId, tabId, rect: message.rect,
          viewportWidth: message.viewportWidth, viewportHeight: message.viewportHeight,
        } satisfies BackgroundMessage);
        sendResponse({ ok: true });
      } catch (error) {
        sendResponse({ ok: false, error: String(error) });
      }
    })();
    return true;
  }
  if (message.type === "reversewarp-request-display-capture") {
    void (async () => {
      try {
        const tabId = _sender.tab?.id;
        if (!tabId) throw new Error("source tab is unavailable");
        const parameters = new URLSearchParams({
          tabId: String(tabId), rect: JSON.stringify(message.rect),
          viewportWidth: String(message.viewportWidth), viewportHeight: String(message.viewportHeight),
        });
        await chrome.windows.create({ url: `capture.html?${parameters}`, type: "popup", width: 430, height: 180 });
        sendResponse({ ok: true });
      } catch (error) {
        sendResponse({ ok: false, error: String(error) });
      }
    })();
    return true;
  }
  if (message.type === "reversewarp-stop") {
    void chrome.runtime.sendMessage({ type: "reversewarp-stop-offscreen" });
    if (session) void nativeRequest({ type: "stopSession", token: session.token });
    session = null;
    sendResponse({ ok: true });
  }
  return false;
});
