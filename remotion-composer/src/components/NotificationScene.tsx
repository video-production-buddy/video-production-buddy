import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { StyleLayerStack, type StyleLayerConfig } from "./StyleLayers";

export interface NotificationSceneProps {
  badgeStart?: number;
  badgeEnd?: number;
  badgeColor?: string;
  banners?: string[];
  backgroundColor?: string;
  sceneDurationSeconds?: number;
  styleLayers?: StyleLayerConfig[];
}

const ICON_COLORS = [
  "#2D5BE3", "#E33D2D", "#2DB365", "#E39B2D",
  "#7B2DE3", "#2DB3B3", "#E32D7B", "#2D8AE3",
  "#6EE32D", "#E36A2D", "#4A4AE3", "#E3CA2D",
  "#2DE3A1", "#A12DE3", "#C83232", "#2DE356",
  "#E32DA1", "#2DC4E3", "#B4C42D", "#E32D56",
];

const BADGED_INDICES = [0, 2, 4, 7, 11, 15];
const BADGE_MULTIPLIERS = [1.0, 0.28, 0.52, 0.19, 0.37, 0.11];

const AppIcon: React.FC<{
  color: string;
  badgeValue: number | null;
  badgeColor: string;
  enterDelay: number;
}> = ({ color, badgeValue, badgeColor, enterDelay }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const iconSpring = spring({
    frame: frame - enterDelay,
    fps,
    config: { damping: 14, stiffness: 130 },
  });

  return (
    <div style={{ position: "relative", flexShrink: 0 }}>
      <div
        style={{
          width: 130,
          height: 130,
          borderRadius: 26,
          background: color,
          opacity: Math.min(1, iconSpring * 0.85),
          transform: `scale(${iconSpring})`,
          willChange: "transform, opacity",
        }}
      />
      {badgeValue !== null && badgeValue > 0 && (
        <div
          style={{
            position: "absolute",
            top: -10,
            right: -10,
            minWidth: 38,
            height: 38,
            borderRadius: 19,
            background: badgeColor,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 19,
            fontWeight: 800,
            color: "#FFFFFF",
            fontFamily: "Inter, system-ui, sans-serif",
            padding: "0 7px",
            boxShadow: `0 0 10px ${badgeColor}88`,
            opacity: iconSpring,
          }}
        >
          {badgeValue > 99 ? "99+" : badgeValue}
        </div>
      )}
    </div>
  );
};

const NotifBanner: React.FC<{
  text: string;
  badgeColor: string;
  stackOffset: number;
  enterFrame: number;
}> = ({ text, badgeColor, stackOffset, enterFrame }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const bannerSpring = spring({
    frame: frame - enterFrame,
    fps,
    config: { damping: 16, stiffness: 140 },
  });

  const slideY = interpolate(bannerSpring, [0, 1], [-260, 0]);

  return (
    <div
      style={{
        position: "absolute",
        top: 60 + stackOffset,
        left: 36,
        right: 36,
        transform: `translateY(${slideY}px)`,
        opacity: bannerSpring,
        background: "rgba(28,28,32,0.92)",
        borderRadius: 18,
        padding: "18px 22px",
        borderLeft: `4px solid ${badgeColor}`,
        willChange: "transform, opacity",
      }}
    >
      <div
        style={{
          fontSize: 22,
          fontWeight: 600,
          color: "#FFFFFF",
          fontFamily: "Inter, system-ui, sans-serif",
          lineHeight: 1.3,
        }}
      >
        {text}
      </div>
    </div>
  );
};

export const NotificationScene: React.FC<NotificationSceneProps> = ({
  badgeStart = 87,
  badgeEnd = 102,
  badgeColor = "#FF3B30",
  banners = [
    "New message from Sarah",
    "Task overdue: Q1 Review",
    "Doc comment: see line 4",
    "Team standup in 5 min",
  ],
  backgroundColor = "#0D0D0D",
  sceneDurationSeconds,
  styleLayers,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const effectiveDuration = sceneDurationSeconds
    ? Math.round(sceneDurationSeconds * fps)
    : durationInFrames;

  const counterProgress = interpolate(
    frame,
    [0, effectiveDuration * 0.8],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  const primaryBadge = Math.round(
    badgeStart + (badgeEnd - badgeStart) * counterProgress
  );

  const glowOpacity = 0.28 + Math.sin(frame / (fps * 1.4)) * 0.12;

  return (
    <AbsoluteFill style={{ background: backgroundColor, overflow: "hidden" }}>
      <StyleLayerStack layers={styleLayers} />
      {/* Ambient badge-red glow */}
      <AbsoluteFill
        style={{
          background: `radial-gradient(ellipse at 50% 45%, rgba(255,59,48,${glowOpacity}) 0%, transparent 65%)`,
          pointerEvents: "none",
        }}
      />

      {/* App icon grid — 4 cols × 5 rows, centered */}
      <AbsoluteFill
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          paddingTop: 120,
        }}
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, 130px)",
            gap: 22,
          }}
        >
          {ICON_COLORS.map((color, idx) => {
            const slot = BADGED_INDICES.indexOf(idx);
            let badgeValue: number | null = null;
            if (slot >= 0) {
              badgeValue = Math.max(
                1,
                Math.round(primaryBadge * BADGE_MULTIPLIERS[slot])
              );
            }
            return (
              <AppIcon
                key={idx}
                color={color}
                badgeValue={badgeValue}
                badgeColor={badgeColor}
                enterDelay={idx * 1.2}
              />
            );
          })}
        </div>
      </AbsoluteFill>

      {/* Notification banners */}
      {banners.slice(0, 4).map((text, idx) => (
        <NotifBanner
          key={idx}
          text={text}
          badgeColor={badgeColor}
          stackOffset={idx * 94}
          enterFrame={Math.round((0.35 + idx * 0.5) * fps)}
        />
      ))}
    </AbsoluteFill>
  );
};
