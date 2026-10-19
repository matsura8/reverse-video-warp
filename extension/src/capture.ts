type CaptureProcessMessage = { type: "reversewarp-process-frame"; frame: number[] };
type CaptureRenderMessage = { type: "reversewarp-render-frame"; frame: number[]; applied: boolean; probability: number };

const button = document.querySelector<HTMLButtonElement>("#start");
const statusElement = document.querySelector<HTMLElement>("#status");
if (!button || !statusElement) throw new Error("capture page controls are missing");

button.addEventListener("click", () => void (async () => {
  button.disabled = true;
  try {
    const parameters = new URLSearchParams(location.search);
    const tabId = Number(parameters.get("tabId"));
    const rect = JSON.parse(parameters.get("rect") ?? "{}") as DOMRectInit;
    const viewportWidth = Number(parameters.get("viewportWidth"));
    const viewportHeight = Number(parameters.get("viewportHeight"));
    const stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true });
    const video = document.createElement("video");
    video.srcObject = stream;
    video.muted = true;
    await video.play();
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d", { alpha: false });
    if (!context) throw new Error("capture canvas is unavailable");
    statusElement.textContent = "Processing locally. Keep this window open; close it to stop.";
    let busy = false;
    const timer = window.setInterval(() => void (async () => {
      if (busy) return;
      busy = true;
      try {
        const scaleX = video.videoWidth / viewportWidth;
        const scaleY = video.videoHeight / viewportHeight;
        const sourceWidth = Math.max(2, Math.round((rect.width ?? 0) * scaleX));
        const sourceHeight = Math.max(2, Math.round((rect.height ?? 0) * scaleY));
        const outputScale = Math.min(1, 640 / sourceWidth);
        canvas.width = Math.max(2, Math.round(sourceWidth * outputScale));
        canvas.height = Math.max(2, Math.round(sourceHeight * outputScale));
        context.drawImage(video, Math.round((rect.x ?? 0) * scaleX), Math.round((rect.y ?? 0) * scaleY), sourceWidth, sourceHeight, 0, 0, canvas.width, canvas.height);
        const blob = await new Promise<Blob>((resolve, reject) => canvas.toBlob((value) => value ? resolve(value) : reject(new Error("display frame encoding failed")), "image/jpeg", 0.82));
        const reply = await chrome.runtime.sendMessage({ type: "reversewarp-process-frame", frame: Array.from(new Uint8Array(await blob.arrayBuffer())) } satisfies CaptureProcessMessage);
        if (!reply?.ok) throw new Error(reply?.error ?? "frame processing failed");
        await chrome.tabs.sendMessage(tabId, { type: "reversewarp-render-frame", frame: reply.frame, applied: reply.applied, probability: reply.probability } satisfies CaptureRenderMessage);
      } catch (error) {
        statusElement.textContent = `Fail-open: ${String(error)}`;
        clearInterval(timer);
        for (const track of stream.getTracks()) track.stop();
      } finally {
        busy = false;
      }
    })(), 100);
    addEventListener("beforeunload", () => {
      clearInterval(timer);
      for (const track of stream.getTracks()) track.stop();
    });
  } catch (error) {
    statusElement.textContent = `Capture was not started: ${String(error)}`;
    button.disabled = false;
  }
})());
