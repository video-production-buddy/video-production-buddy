import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { StyleLayerStack, type StyleLayerConfig } from "./StyleLayers";

export interface StatRollSceneProps {
  targetValue: number;
  unitLabel?: string;
  subtitle?: string;
  accentColor?: string;
  backgroundColor?: string;
  rollDurationSeconds?: number;
  sceneDurationSeconds?: number;
  styleLayers?: StyleLayerConfig[];
}

const formatNumber = (n: number): string => {
  return Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
};

// Implements: digit_roll_up, comma_separators, unit_label_fade
export const StatRollScene: React.FC<StatRollSceneProps> = ({
  targetValue,
  unitLabel = "",
  subtitle = "",
  accentColor = "#34D399",
  backgroundColor = "#1E1B4B",
  rollDurationSeconds = 1.4,
  sceneDurationSeconds,
  styleLayers,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const totalFrames = sceneDurationSeconds
    ? Math.round(sceneDurationSeconds * fps)
    : durationInFrames;
  void totalFrames;

  const rollFrames = Math.round(rollDurationSeconds * fps);
  const rollSpring = spring({
    frame,
    fps,
    durationInFrames: rollFrames,
    config: { damping: 20, stiffness: 80 },
  });
  const currentValue = rollSpring * targetValue;
  const display = formatNumber(currentValue);

  const unitFadeStart = Math.round(rollFrames * 0.85);
  const unitSpring = spring({
    frame: frame - unitFadeStart,
    fps,
    config: { damping: 22, stiffness: 100 },
  });

  const subStart = Math.round(fps * (rollDurationSeconds + 0.3));
  const subSpring = spring({
    frame: frame - subStart,
    fps,
    config: { damping: 22, stiffness: 90 },
  });

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
          background: `radial-gradient(ellipse at 50% 50%, ${accentColor}22 0%, transparent 55%)`,
          pointerEvents: "none",
        }}
      />

      <div style={{ display: "flex", alignItems: "baseline", gap: 18 }}>
        <div
          style={{
            fontSize: 220,
            fontWeight: 800,
            color: "#FFFFFF",
            fontFamily: "Inter, system-ui, sans-serif",
            letterSpacing: "-0.05em",
            lineHeight: 1,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {display}
        </div>
        {unitLabel && (
          <div
            style={{
              fontSize: 56,
              fontWeight: 600,
              color: accentColor,
              fontFamily: "Inter, system-ui, sans-serif",
              opacity: unitSpring,
              transform: `translateY(${interpolate(unitSpring, [0, 1], [16, 0])}px)`,
              willChange: "transform, opacity",
            }}
          >
            {unitLabel}
          </div>
        )}
      </div>

      {subtitle && (
        <div
          style={{
            marginTop: 32,
            fontSize: 32,
            fontWeight: 400,
            color: "rgba(255,255,255,0.78)",
            fontFamily: "Inter, system-ui, sans-serif",
            letterSpacing: "0.01em",
            opacity: subSpring,
            transform: `translateY(${interpolate(subSpring, [0, 1], [12, 0])}px)`,
            willChange: "transform, opacity",
          }}
        >
          {subtitle}
        </div>
      )}
    </AbsoluteFill>
  );
};
