import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { StyleLayerStack, type StyleLayerConfig } from "./StyleLayers";

export interface BadgeFreezeSceneProps {
  startCount?: number;
  endCount?: number;
  accentColor?: string;
  backgroundColor?: string;
  freezeAtSeconds?: number;
  showThumb?: boolean;
  sceneDurationSeconds?: number;
  styleLayers?: StyleLayerConfig[];
}

// Implements: counter_roll, thumb_silhouette_swipe, freeze_pulse
export const BadgeFreezeScene: React.FC<BadgeFreezeSceneProps> = ({
  startCount = 87,
  endCount = 102,
  accentColor = "#FF3B30",
  backgroundColor = "#0D0D0D",
  freezeAtSeconds = 1.5,
  showThumb = true,
  sceneDurationSeconds,
  styleLayers,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames, width, height } = useVideoConfig();
  const totalFrames = sceneDurationSeconds
    ? Math.round(sceneDurationSeconds * fps)
    : durationInFrames;
  void totalFrames;

  const freezeFrame = Math.round(freezeAtSeconds * fps);

  const rollProgress = interpolate(frame, [0, freezeFrame], [0, 1], {
    extrapolateRight: "clamp",
  });
  const currentCount = Math.round(
    interpolate(rollProgress, [0, 1], [startCount, endCount])
  );
  const displayCount = currentCount > 99 ? "99+" : String(currentCount);

  const pulseEnd = freezeFrame + Math.round(fps * 0.4);
  const pulseScale = interpolate(
    frame,
    [freezeFrame, freezeFrame + Math.round(fps * 0.2), pulseEnd],
    [1.0, 1.15, 1.0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const flashOpacity = interpolate(
    frame,
    [freezeFrame, freezeFrame + Math.round(fps * 0.15), freezeFrame + Math.round(fps * 0.5)],
    [0, 0.7, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const thumbStart = Math.round(fps * 0.6);
  const thumbEnter = spring({
    frame: frame - thumbStart,
    fps,
    config: { damping: 18, stiffness: 80 },
  });
  const thumbSwipe = interpolate(
    frame,
    [thumbStart, freezeFrame],
    [0, 0.65],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  const thumbY = interpolate(thumbEnter, [0, 1], [height * 0.9, height * 0.55]);
  const thumbX = interpolate(thumbSwipe, [0, 1], [width * 0.4, width * 0.78]);

  return (
    <AbsoluteFill
      style={{
        background: backgroundColor,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <StyleLayerStack layers={styleLayers} />

      <AbsoluteFill
        style={{
          background: `radial-gradient(ellipse at 50% 45%, ${accentColor}66 0%, transparent 60%)`,
          opacity: 0.5 + 0.15 * Math.sin(frame / (fps * 0.8)),
          pointerEvents: "none",
        }}
      />

      <AbsoluteFill
        style={{
          boxShadow: "inset 0 0 200px rgba(0,0,0,0.7)",
          pointerEvents: "none",
        }}
      />

      <div
        style={{
          width: 520,
          height: 520,
          borderRadius: "50%",
          background: accentColor,
          boxShadow: `0 0 200px ${accentColor}88, 0 30px 90px rgba(0,0,0,0.5)`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          transform: `scale(${pulseScale})`,
          willChange: "transform",
          position: "relative",
        }}
      >
        <div
          style={{
            fontSize: displayCount.length >= 3 ? 220 : 280,
            fontWeight: 800,
            color: "#FFFFFF",
            fontFamily: "Inter, system-ui, sans-serif",
            letterSpacing: "-0.04em",
          }}
        >
          {displayCount}
        </div>
        <div
          style={{
            position: "absolute",
            inset: 0,
            borderRadius: "50%",
            background: "#FFFFFF",
            opacity: flashOpacity,
            pointerEvents: "none",
          }}
        />
      </div>

      {showThumb && (
        <div
          style={{
            position: "absolute",
            left: thumbX,
            top: thumbY,
            transform: "translate(-50%, -50%) rotate(-15deg)",
            opacity: 0.85,
            willChange: "transform, top, left",
          }}
        >
          <svg width="180" height="240" viewBox="0 0 60 80">
            <path
              d="M28 78 C 18 78, 12 70, 12 60 L 12 40 C 12 32, 16 28, 22 28 L 22 14 C 22 8, 26 4, 30 4 C 34 4, 38 8, 38 14 L 38 28 L 46 28 C 52 28, 56 32, 56 38 L 56 60 C 56 70, 50 78, 40 78 Z"
              fill="#1A1A1A"
              stroke="rgba(255,255,255,0.18)"
              strokeWidth="0.8"
            />
          </svg>
        </div>
      )}
    </AbsoluteFill>
  );
};
