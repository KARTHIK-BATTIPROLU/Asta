import React, { forwardRef, useImperativeHandle, useCallback, useEffect, useRef, useState } from "react";
import { createOrbScene, type OrbSceneApi } from "./orbScene";
import { HandTracker, type TrackerStatus } from "./handTracker";
import "./ultron.css";

type CameraState = "off" | "starting" | "on" | "error";

const MODE_LABEL: Record<TrackerStatus["mode"], string> = {
  idle: "STANDBY",
  spin: "SPIN",
  zoom: "ZOOM",
};

interface JarvisOrbProps {
  messages?: any[];
  inputText?: string;
  setInputText?: (v: string) => void;
  handleTextSubmit?: (e: React.FormEvent) => void;
  isRecording?: boolean;
  startRecording?: () => void;
  stopRecording?: () => void;
  astaState?: string;
  astaStatus?: string;
}

const JarvisOrb = forwardRef<any, JarvisOrbProps>((props, ref) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const overlayRef = useRef<HTMLCanvasElement>(null);
  const sceneRef = useRef<OrbSceneApi | null>(null);
  const trackerRef = useRef<HandTracker | null>(null);

  const [camera, setCamera] = useState<CameraState>("off");
  const [status, setStatus] = useState<TrackerStatus>({ hands: 0, mode: "idle" });
  const [error, setError] = useState<string | null>(null);

  useImperativeHandle(ref, () => ({
    setAstaState: (state: "idle" | "listening" | "thinking" | "speaking") => {
      sceneRef.current?.setAstaState(state);
    }
  }));

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const scene = createOrbScene(container);
    sceneRef.current = scene;
    return () => {
      trackerRef.current?.stop();
      trackerRef.current = null;
      scene.dispose();
      sceneRef.current = null;
    };
  }, []);

  const stopGestures = useCallback(() => {
    trackerRef.current?.stop();
    trackerRef.current = null;
    setCamera("off");
    setStatus({ hands: 0, mode: "idle" });
  }, []);

  const startGestures = useCallback(async () => {
    const video = videoRef.current;
    const overlay = overlayRef.current;
    if (!video || !overlay || trackerRef.current) return;

    setCamera("starting");
    setError(null);

    const tracker = new HandTracker(video, overlay, {
      onRotate: (dt, dp) => sceneRef.current?.rotateBy(dt, dp),
      onZoom: (factor) => sceneRef.current?.zoomBy(factor),
      onStatus: setStatus,
    });
    trackerRef.current = tracker;

    try {
      await tracker.start();
      setCamera("on");
    } catch (err) {
      trackerRef.current = null;
      tracker.stop();
      setCamera("error");
      setError(
        err instanceof DOMException && err.name === "NotAllowedError"
          ? "CAMERA ACCESS DENIED"
          : "TRACKING INIT FAILED",
      );
    }
  }, []);

  const toggleGestures = useCallback(() => {
    if (trackerRef.current) stopGestures();
    else void startGestures();
  }, [startGestures, stopGestures]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      switch (e.key) {
        case "+":
        case "=":
          sceneRef.current?.zoomIn();
          break;
        case "-":
        case "_":
          sceneRef.current?.zoomOut();
          break;
        case "r":
        case "R":
          sceneRef.current?.resetView();
          break;
        case "g":
        case "G":
          toggleGestures();
          break;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleGestures]);

  const cameraOn = camera === "on";

  return (
    <>
      <div ref={containerRef} className="orb-root" />

      <div className="overlay-vignette" />
      <div className="overlay-grain" />
      <div className="overlay-scanlines" />

      <div className="hud hud-title">U.L.T.R.O.N.</div>

      <div className="hud hud-hint">
        <div>
          <span className="key">DRAG</span> spin&nbsp;&nbsp;
          <span className="key">SCROLL</span> zoom
        </div>
        {cameraOn ? (
          <div>
            <span className="key">PINCH + MOVE</span> spin&nbsp;&nbsp;
            <span className="key">PINCH BOTH HANDS ± SPREAD</span> zoom
          </div>
        ) : (
          <div>
            <span className="key">G</span> hand gestures&nbsp;&nbsp;
            <span className="key">R</span> reset&nbsp;&nbsp;
            <span className="key">+/−</span> zoom
          </div>
        )}
      </div>

      <div className="hud hud-controls">
        <div className={`camera-panel${cameraOn ? " visible" : ""}`}>
          {/* Mirrored preview so it behaves like a mirror */}
          <video ref={videoRef} muted playsInline className="camera-video" />
          <canvas ref={overlayRef} width={208} height={156} className="camera-overlay" />
          <div className="camera-status">
            {status.hands > 0
              ? `${status.hands} HAND${status.hands > 1 ? "S" : ""} · ${MODE_LABEL[status.mode]}`
              : "SHOW HANDS"}
          </div>
        </div>

        {error && <div className="hud-error">{error}</div>}

        <div className="hud-row">
          <button
            type="button"
            className="hud-btn"
            aria-pressed={cameraOn}
            onClick={toggleGestures}
            disabled={camera === "starting"}
          >
            {camera === "starting" ? "INITIALIZING…" : cameraOn ? "GESTURES ON" : "GESTURES OFF"}
          </button>
        </div>
        <div className="hud-row">
          <button type="button" className="hud-btn" onClick={() => sceneRef.current?.zoomIn()} aria-label="Zoom in">
            +
          </button>
          <button type="button" className="hud-btn" onClick={() => sceneRef.current?.zoomOut()} aria-label="Zoom out">
            −
          </button>
          <button type="button" className="hud-btn" onClick={() => sceneRef.current?.resetView()}>
            RESET
          </button>
        </div>

        {/* ASTA INTEGRATION */}
        <div style={{ marginTop: "20px", borderTop: "1px solid rgba(48,170,255,0.3)", paddingTop: "10px" }}>
          <div className="camera-status" style={{ marginBottom: "10px", color: props.astaState === 'PROCESSING' ? '#ffaa30' : '#30aaff' }}>
            ASTA: {props.astaStatus || 'DISCONNECTED'}
          </div>
          
          <div className="hud-row">
            <button 
              type="button" 
              className="hud-btn" 
              onClick={props.isRecording ? props.stopRecording : props.startRecording}
              style={{ color: props.isRecording ? '#ff4444' : '#30aaff' }}
            >
              {props.isRecording ? "STOP MIC" : "START MIC"}
            </button>
          </div>
          
          <form onSubmit={props.handleTextSubmit} style={{ display: "flex", gap: "5px", marginTop: "10px" }}>
            <input 
              type="text" 
              className="hud-btn"
              style={{ flex: 1, cursor: "text", background: "rgba(0,0,0,0.5)", border: "1px solid rgba(48, 170, 255, 0.4)", color: "#fff", padding: "5px 10px" }}
              placeholder="Type a message..."
              value={props.inputText || ""}
              onChange={(e) => props.setInputText && props.setInputText(e.target.value)}
            />
            <button type="submit" className="hud-btn">SEND</button>
          </form>
        </div>
      </div>

      {/* Subtitles for ASTA responses */}
      <div className="hud" style={{ position: "absolute", bottom: "30px", left: "40px", maxWidth: "40vw", color: "#f8fafc", fontFamily: "monospace", fontSize: "14px", lineHeight: "1.5", textShadow: "0 0 4px rgba(48, 170, 255, 0.5)", pointerEvents: "none" }}>
        {props.messages && props.messages.filter(m => m.role === 'assistant').slice(-1).map((msg, idx) => (
          <div key={idx} className="bubble">
            {msg.content.replace(/\{"action".*?\}/gs, '').trim()}
          </div>
        ))}
      </div>
    </>
  );
});

export default JarvisOrb;

