import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { StyleLayerStack, type StyleLayerConfig } from "./StyleLayers";

export interface CheckmarkSceneProps {
  accentColor?: string;
  backgroundColor?: string;
  label?: string;
  sceneDurationSeconds?: number;
  styleLayers?: StyleLayerConfig[];
}

// Implements motion primitives: checkmark_draw, radial_ripple, spring_pop, label_fade
export const CheckmarkScene: React.FC<CheckmarkSceneProps> = ({
  accentColor = "#34D399",
  backgroundColor = "#1E1B4B",
  label = "",
  sceneDurationSeconds,
  styleLayers,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const totalFrames = sceneDurationSeconds
    ? Math.round(sceneDurationSeconds * fps)
    : durationInFrames;
  void totalFrames;

  // spring_pop on the disc — scale 0→1.2→1.0 over 0.3s
  const popProgress = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 200 },
  });
  const overshoot = interpolate(popProgress, [0, 0.5, 1], [0, 1.2, 1.0], {
    extrapolateRight: "clamp",
  });

  // checkmark_draw — strokeDashoffset 0→full over 0.2s ease-in
  const checkPathLength = 90;
  const drawStart = Math.round(fps * 0.05);
  const drawEnd = drawStart + Math.round(fps * 0.2);
  const drawProgress = interpolate(frame, [drawStart, drawEnd], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const dashOffset = checkPathLength * (1 - drawProgress);

  // radial_ripple — circle scale 0→3 with opacity 0.6→0 over 0.8s starting at 0.2s
  const rippleStart = Math.round(fps * 0.2);
  const rippleEnd = rippleStart + Math.round(fps * 0.8);
  const rippleScale = interpolate(frame, [rippleStart, rippleEnd], [0, 3], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const rippleOpacity = interpolate(frame, [rippleStart, rippleEnd], [0.6, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Second ripple for richer atmosphere
  const ripple2Start = Math.round(fps * 0.4);
  const ripple2End = ripple2Start + Math.round(fps * 0.9);
  const ripple2Scale = interpolate(frame, [ripple2Start, ripple2End], [0, 2.5], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const ripple2Opacity = interpolate(frame, [ripple2Start, ripple2End], [0.4, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // label fades in 0.55s after scene start
  const labelStart = Math.round(fps * 0.55);
  const labelSpring = spring({
    frame: frame - labelStart,
    fps,
    config: { damping: 22, stiffness: 90 },
  });

  // Idle pulse on the disc once initial pop is done
  const settledStart = Math.round(fps * 1.2);
  const idlePulse = 1 + Math.sin(Math.max(0, frame - settledStart) / (fps * 0.7)) * 0.015;

  const circleSize = 280;

  return (
    <AbsoluteFill
      style={{
        background: backgroundColor,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <StyleLayerStack layers={styleLayers} />

      <AbsoluteFill
        style={{
          background: `radial-gradient(ellipse at 50% 50%, ${accentColor}33 0%, transparent 55%)`,
          opacity: 0.6,
          pointerEvents: "none",
        }}
      />

      <div
        style={{
          position: "absolute",
          width: circleSize,
          height: circleSize,
          borderRadius: "50%",
          border: `4px solid ${accentColor}`,
          transform: `scale(${rippleScale})`,
          opacity: rippleOpacity,
          willChange: "transform, opacity",
        }}
      />
      <div
        style={{
          position: "absolute",
          width: circleSize,
          height: circleSize,
          borderRadius: "50%",
          border: `3px solid ${accentColor}`,
          transform: `scale(${ripple2Scale})`,
          opacity: ripple2Opacity,
          willChange: "transform, opacity",
        }}
      />

      <div
        style={{
          width: circleSize,
          height: circleSize,
          borderRadius: "50%",
          background: accentColor,
          boxShadow: `0 30px 80px ${accentColor}55, 0 0 60px ${accentColor}44 inset`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          transform: `scale(${overshoot * idlePulse})`,
          willChange: "transform",
        }}
      >
        <svg width="160" height="160" viewBox="0 0 100 100" fill="none">
          <path
            d="M22 52 L42 72 L78 32"
            stroke="#FFFFFF"
            strokeWidth="10"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeDasharray={checkPathLength}
            strokeDashoffset={dashOffset}
          />
        </svg>
      </div>

      {label && (
        <div
          style={{
            marginTop: 56,
            fontSize: 38,
            fontWeight: 600,
            color: "rgba(255,255,255,0.92)",
            letterSpacing: "0.02em",
            fontFamily: "Inter, system-ui, sans-serif",
            opacity: labelSpring,
            transform: `translateY(${interpolate(labelSpring, [0, 1], [16, 0])}px)`,
            willChange: "transform, opacity",
          }}
        >
          {label}
        </div>
      )}
    </AbsoluteFill>
  );
};
