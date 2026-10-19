type ExtensionMessage =
  | { type: "reversewarp-start" }
  | { type: "reversewarp-process-frame"; frame: number[] }
  | { type: "reversewarp-request-tab-capture"; rect: DOMRectInit; viewportWidth: number; viewportHeight: number }
  | { type: "reversewarp-request-display-capture"; rect: DOMRectInit; viewportWidth: number; viewportHeight: number }
  | { type: "reversewarp-render-frame"; frame: number[]; applied: boolean; probability: number }
  | { type: "reversewarp-stop" };

type ReverseWarpWindow = Window & typeof globalThis & {
  __reverseWarpController?: ReverseWarpController;
};
const reverseWarpWindow = window as ReverseWarpWindow;

function supportsOffscreenTabCapture(): boolean {
  return chrome.runtime.getManifest().permissions?.includes("offscreen") ?? false;
}

function largestPlayingVideo(): HTMLVideoElement | null {
  return Array.from(document.querySelectorAll("video"))
    .filter((video) => video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && video.getBoundingClientRect().width > 80)
    .sort((left, right) => {
      const a = left.getBoundingClientRect();
      const b = right.getBoundingClientRect();
      return b.width * b.height - a.width * a.height;
    })[0] ?? null;
}

function largestVisiblePlayerFrame(): HTMLIFrameElement | null {
  return Array.from(document.querySelectorAll("iframe"))
    .filter((frame) => {
      const rect = frame.getBoundingClientRect();
      return rect.width > 240 && rect.height > 135;
    })
    .sort((left, right) => {
      const a = left.getBoundingClientRect();
      const b = right.getBoundingClientRect();
      return b.width * b.height - a.width * a.height;
    })[0] ?? null;
}

class ReverseWarpController {
  private readonly source: HTMLVideoElement | HTMLIFrameElement;
  private readonly capture = document.createElement("canvas");
  private readonly output = document.createElement("canvas");
  private readonly player = document.createElement("video");
  private readonly chrome = document.createElement("div");
  private stopped = false;
  private busy = false;
  private failures = 0;
  private fallbackRequested = false;
  private timer = 0;
  private readonly observer: ResizeObserver;

  constructor(source: HTMLVideoElement | HTMLIFrameElement) {
    this.source = source;
    this.player.autoplay = true;
    this.player.muted = true;
    this.player.playsInline = true;
    this.player.srcObject = this.output.captureStream(12);
    Object.assign(this.player.style, {
      position: "fixed", zIndex: "2147483645", objectFit: "fill", pointerEvents: "none",
      background: "black",
    });
    this.chrome.textContent = "Estimated reconstruction · starting · Stop";
    Object.assign(this.chrome.style, {
      position: "fixed", zIndex: "2147483646", color: "white", background: "rgba(0,0,0,.82)",
      font: "600 12px system-ui", padding: "6px 9px", borderRadius: "5px", cursor: "pointer",
    });
    this.chrome.addEventListener("click", () => this.stop());
    document.documentElement.append(this.player, this.chrome);
    this.observer = new ResizeObserver(() => this.position());
    this.observer.observe(source);
    addEventListener("scroll", this.position, true);
    addEventListener("resize", this.position);
    this.position();
  }

  start(): void {
    if (this.source instanceof HTMLIFrameElement) {
      void this.requestTabCapture();
      return;
    }
    this.timer = window.setInterval(() => void this.tick(), 83);
    void this.tick();
  }

  private async requestTabCapture(): Promise<void> {
    if (this.stopped || this.fallbackRequested) return;
    this.fallbackRequested = true;
    clearInterval(this.timer);
    const rect = this.source.getBoundingClientRect();
    const response = await chrome.runtime.sendMessage({
      type: supportsOffscreenTabCapture() ? "reversewarp-request-tab-capture" : "reversewarp-request-display-capture",
      rect: rect.toJSON(), viewportWidth: innerWidth, viewportHeight: innerHeight,
    } satisfies ExtensionMessage);
    if (response?.ok) {
      this.chrome.textContent = "Estimated reconstruction · tab capture · Stop";
      return;
    }
    this.stop(new Error(response?.error ?? "browser capture fallback failed"));
  }

  private readonly position = (): void => {
    const rect = this.source.getBoundingClientRect();
    Object.assign(this.player.style, { left: `${rect.left}px`, top: `${rect.top}px`, width: `${rect.width}px`, height: `${rect.height}px` });
    Object.assign(this.chrome.style, { left: `${rect.left + 8}px`, top: `${rect.top + 8}px` });
  };

  private async tick(): Promise<void> {
    if (!(this.source instanceof HTMLVideoElement) || this.stopped || this.busy || this.source.paused || this.source.ended) return;
    this.busy = true;
    try {
      const scale = Math.min(1, 640 / this.source.videoWidth);
      const width = Math.max(2, Math.round(this.source.videoWidth * scale));
      const height = Math.max(2, Math.round(this.source.videoHeight * scale));
      this.capture.width = width;
      this.capture.height = height;
      this.capture.getContext("2d", { alpha: false })?.drawImage(this.source, 0, 0, width, height);
      const blob = await new Promise<Blob>((resolve, reject) => this.capture.toBlob((value) => value ? resolve(value) : reject(new Error("frame encoding failed")), "image/jpeg", 0.82));
      const reply = await chrome.runtime.sendMessage({ type: "reversewarp-process-frame", frame: Array.from(new Uint8Array(await blob.arrayBuffer())) } satisfies ExtensionMessage);
      if (!reply?.ok) throw new Error(reply?.error ?? "frame processing failed");
      const bitmap = await createImageBitmap(new Blob([new Uint8Array(reply.frame)], { type: "image/jpeg" }));
      this.output.width = bitmap.width;
      this.output.height = bitmap.height;
      this.output.getContext("2d", { alpha: false })?.drawImage(bitmap, 0, 0);
      bitmap.close();
      this.player.style.visibility = "visible";
      this.chrome.textContent = `Estimated reconstruction · ${reply.applied ? "corrected" : "bypass"} · ${(reply.probability * 100).toFixed(1)}% · Stop`;
      this.failures = 0;
    } catch (error) {
      if (!this.fallbackRequested && error instanceof DOMException && error.name === "SecurityError") {
        await this.requestTabCapture();
        return;
      }
      this.failures += 1;
      this.chrome.textContent = `Estimated reconstruction · fail-open ${this.failures}/3 · Stop`;
      this.player.style.visibility = "hidden";
      if (this.failures >= 3) this.stop(error);
    } finally {
      this.busy = false;
    }
  }

  async render(frame: number[], applied: boolean, probability: number): Promise<void> {
    if (this.stopped) return;
    const bitmap = await createImageBitmap(new Blob([new Uint8Array(frame)], { type: "image/jpeg" }));
    this.output.width = bitmap.width;
    this.output.height = bitmap.height;
    this.output.getContext("2d", { alpha: false })?.drawImage(bitmap, 0, 0);
    bitmap.close();
    this.player.style.visibility = "visible";
    this.chrome.textContent = `Estimated reconstruction · ${applied ? "corrected" : "bypass"} · ${(probability * 100).toFixed(1)}% · Stop`;
  }

  stop(reason?: unknown): void {
    if (this.stopped) return;
    this.stopped = true;
    clearInterval(this.timer);
    this.observer.disconnect();
    removeEventListener("scroll", this.position, true);
    removeEventListener("resize", this.position);
    for (const track of (this.player.srcObject as MediaStream | null)?.getTracks() ?? []) track.stop();
    this.player.remove();
    this.chrome.remove();
    reverseWarpWindow.__reverseWarpController = undefined;
    void chrome.runtime.sendMessage({ type: "reversewarp-stop" } satisfies ExtensionMessage);
    if (reason) console.error("ReverseWarp stopped fail-open", reason);
  }
}

chrome.runtime.onMessage.addListener((message: ExtensionMessage) => {
  if (message.type === "reversewarp-render-frame") {
    void reverseWarpWindow.__reverseWarpController?.render(message.frame, message.applied, message.probability);
    return;
  }
  if (message.type !== "reversewarp-start") return;
  reverseWarpWindow.__reverseWarpController?.stop();
  const source = largestPlayingVideo() ?? largestVisiblePlayerFrame();
  if (!source) throw new Error("ReverseWarp found no visible playable video or embedded player");
  const controller = new ReverseWarpController(source);
  reverseWarpWindow.__reverseWarpController = controller;
  controller.start();
});
