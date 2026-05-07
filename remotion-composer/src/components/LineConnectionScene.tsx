import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { StyleLayerStack, type StyleLayerConfig } from "./StyleLayers";

export interface LineConnectionSceneProps {
  leftLabel: string;
  rightLabel: string;
  leftSubLabel?: string;
  rightSubLabel?: string;
  accentColor?: string;
  backgroundColor?: string;
  drawDelay?: number;
  sceneDurationSeconds?: number;
  styleLayers?: StyleLayerConfig[];
}

// Implements: line_draw_between_anchors, mutual_highlight_pulse
export const LineConnectionScene: React.FC<LineConnectionSceneProps> = ({
  leftLabel,
  rightLabel,
  leftSubLabel = "",
  rightSubLabel = "",
  accentColor = "#34D399",
  backgroundColor = "#1E1B4B",
  drawDelay = 0.6,
  sceneDurationSeconds,
  styleLayers,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames, width, height } = useVideoConfig();
  const totalFrames = sceneDurationSeconds
    ? Math.round(sceneDurationSeconds * fps)
    : durationInFrames;
  void totalFrames;

  const cardW = Math.min(420, Math.round(width * 0.42));
  const cardH = 200;
  const leftAnchor = { x: cardW / 2 + 80, y: height / 2 };
  const rightAnchor = { x: width - cardW / 2 - 80, y: height / 2 };

  const leftSpring = spring({ frame, fps, config: { damping: 18, stiffness: 120 } });
  const leftOpacity = leftSpring;
  const leftX = interpolate(leftSpring, [0, 1], [-60, 0]);

  const rightStart = Math.round(fps * 0.2);
  const rightSpring = spring({
    frame: frame - rightStart,
    fps,
    config: { damping: 18, stiffness: 120 },
  });
  const rightOpacity = rightSpring;
  const rightX = interpolate(rightSpring, [0, 1], [60, 0]);

  const drawStart = Math.round(fps * drawDelay);
  const drawEnd = drawStart + Math.round(fps * 0.4);
  const drawProgress = interpolate(frame, [drawStart, drawEnd], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const highlightPulse = interpolate(
    frame,
    [drawEnd, drawEnd + Math.round(fps * 0.15), drawEnd + Math.round(fps * 0.55)],
    [0, 1, 0.6],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const ctrlY = leftAnchor.y - 50;
  const pathD = `M ${leftAnchor.x} ${leftAnchor.y} Q ${(leftAnchor.x + rightAnchor.x) / 2} ${ctrlY}, ${rightAnchor.x} ${rightAnchor.y}`;
  const pathLength = Math.hypot(rightAnchor.x - leftAnchor.x, rightAnchor.y - leftAnchor.y) * 1.05;

  return (
    <AbsoluteFill style={{ background: backgroundColor }}>
      <StyleLayerStack layers={styleLayers} />

      <AbsoluteFill
        style={{
          background: `radial-gradient(ellipse at 50% 50%, ${accentColor}1f 0%, transparent 60%)`,
          pointerEvents: "none",
        }}
      />

      <svg
        width={width}
        height={height}
        style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
      >
        <defs>
          <filter id="line-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="6" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <path
          d={pathD}
          fill="none"
          stroke={accentColor}
          strokeWidth="4"
          strokeLinecap="round"
          strokeDasharray={pathLength}
          strokeDashoffset={pathLength * (1 - drawProgress)}
          filter="url(#line-glow)"
          opacity={0.95}
        />
      </svg>

      <Card
        x={leftAnchor.x}
        y={leftAnchor.y}
        w={cardW}
        h={cardH}
        label={leftLabel}
        subLabel={leftSubLabel}
        opacity={leftOpacity}
        translateX={leftX}
        accentColor={accentColor}
        highlight={highlightPulse}
      />

      <Card
        x={rightAnchor.x}
        y={rightAnchor.y}
        w={cardW}
        h={cardH}
        label={rightLabel}
        subLabel={rightSubLabel}
        opacity={rightOpacity}
        translateX={rightX}
        accentColor={accentColor}
        highlight={highlightPulse}
      />
    </AbsoluteFill>
  );
};

const Card: React.FC<{
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
  subLabel: string;
  opacity: number;
  translateX: number;
  accentColor: string;
  highlight: number;
}> = ({ x, y, w, h, label, subLabel, opacity, translateX, accentColor, highlight }) => {
  const borderAlpha = Math.round(highlight * 0.95 * 255).toString(16).padStart(2, "0");
  const glowAlpha = Math.round(highlight * 0.45 * 255).toString(16).padStart(2, "0");
  return (
    <div
      style={{
        position: "absolute",
        left: x - w / 2,
        top: y - h / 2,
        width: w,
        height: h,
        background: "#0F0E2C",
        border: `1px solid ${accentColor}${borderAlpha}`,
        borderRadius: 16,
        padding: "20px 26px",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        boxShadow: `0 12px 40px rgba(0,0,0,0.4), 0 0 ${24 + 30 * highlight}px ${accentColor}${glowAlpha}`,
        opacity,
        transform: `translateX(${translateX}px)`,
        willChange: "transform, opacity, box-shadow",
      }}
    >
      <div
        style={{
          fontSize: 32,
          fontWeight: 700,
          color: "#FFFFFF",
          fontFamily: "Inter, system-ui, sans-serif",
          letterSpacing: "-0.01em",
        }}
      >
        {label}
      </div>
      {subLabel && (
        <div
          style={{
            marginTop: 8,
            fontSize: 18,
            fontWeight: 400,
            color: "rgba(255,255,255,0.65)",
            fontFamily: "Inter, system-ui, sans-serif",
          }}
        >
          {subLabel}
        </div>
      )}
    </div>
  );
};
