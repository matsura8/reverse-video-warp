type OffscreenMessage =
  | { type: "reversewarp-start-offscreen"; streamId: string; tabId: number; rect: DOMRectInit; viewportWidth: number; viewportHeight: number }
  | { type: "reversewarp-process-frame"; frame: number[] }
  | { type: "reversewarp-render-frame"; tabId: number; frame: number[]; applied: boolean; probability: number }
  | { type: "reversewarp-stop-offscreen" };

let tracks: MediaStreamTrack[] = [];
let timer = 0;
let busy = false;

function stopCapture(): void {
  clearInterval(timer);
  for (const track of tracks) track.stop();
  tracks = [];
  busy = false;
}

async function startCapture(message: Extract<OffscreenMessage, { type: "reversewarp-start-offscreen" }>): Promise<void> {
  stopCapture();
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { mandatory: { chromeMediaSource: "tab", chromeMediaSourceId: message.streamId } } as MediaTrackConstraints,
    video: { mandatory: { chromeMediaSource: "tab", chromeMediaSourceId: message.streamId } } as MediaTrackConstraints,
  });
  tracks = stream.getTracks();
  const audioContext = new AudioContext();
  if (stream.getAudioTracks().length > 0) audioContext.createMediaStreamSource(stream).connect(audioContext.destination);
  const video = document.createElement("video");
  video.srcObject = new MediaStream(stream.getVideoTracks());
  video.muted = true;
  await video.play();
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d", { alpha: false });
  if (!context) throw new Error("offscreen canvas is unavailable");

  const tick = async (): Promise<void> => {
    if (busy || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return;
    busy = true;
    try {
      const scaleX = video.videoWidth / message.viewportWidth;
      const scaleY = video.videoHeight / message.viewportHeight;
      const sourceWidth = Math.max(2, Math.round((message.rect.width ?? 0) * scaleX));
      const sourceHeight = Math.max(2, Math.round((message.rect.height ?? 0) * scaleY));
      const outputScale = Math.min(1, 640 / sourceWidth);
      canvas.width = Math.max(2, Math.round(sourceWidth * outputScale));
      canvas.height = Math.max(2, Math.round(sourceHeight * outputScale));
      context.drawImage(video, Math.round((message.rect.x ?? 0) * scaleX), Math.round((message.rect.y ?? 0) * scaleY), sourceWidth, sourceHeight, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise<Blob>((resolve, reject) => canvas.toBlob((value) => value ? resolve(value) : reject(new Error("tab frame encoding failed")), "image/jpeg", 0.82));
      const reply = await chrome.runtime.sendMessage({ type: "reversewarp-process-frame", frame: Array.from(new Uint8Array(await blob.arrayBuffer())) } satisfies OffscreenMessage);
      if (!reply?.ok) throw new Error(reply?.error ?? "frame processing failed");
      await chrome.runtime.sendMessage({
        type: "reversewarp-render-frame", tabId: message.tabId,
        frame: reply.frame, applied: reply.applied, probability: reply.probability,
      } satisfies OffscreenMessage);
    } finally {
      busy = false;
    }
  };
  timer = window.setInterval(() => void tick(), 100);
  void tick();
}

chrome.runtime.onMessage.addListener((message: OffscreenMessage) => {
  if (message.type === "reversewarp-start-offscreen") void startCapture(message);
  if (message.type === "reversewarp-stop-offscreen") stopCapture();
});
