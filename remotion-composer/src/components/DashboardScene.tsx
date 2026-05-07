import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { StyleLayerStack, type StyleLayerConfig } from "./StyleLayers";

export interface DashboardSceneProps {
  primaryColor?: string;
  accentColor?: string;
  toastText?: string;
  toastDelay?: number;
  sidebarItems?: string[];
  panelTitle?: string;
  sceneDurationSeconds?: number;
  styleLayers?: StyleLayerConfig[];
}

const DEFAULT_SIDEBAR = ["Tasks", "Messages", "Docs", "Calendar"];

const DEFAULT_TASKS = [
  { label: "Set up client workspace", done: true, active: false },
  { label: "Review Q1 roadmap", done: false, active: true },
  { label: "Schedule team sync", done: false, active: false },
];

export const DashboardScene: React.FC<DashboardSceneProps> = ({
  primaryColor = "#1E1B4B",
  accentColor = "#34D399",
  toastText = "Everything's here.",
  toastDelay = 1.2,
  sidebarItems = DEFAULT_SIDEBAR,
  panelTitle = "Q1 Project",
  styleLayers,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const toastFrame = Math.round(toastDelay * fps);
  const toastSpring = spring({
    frame: frame - toastFrame,
    fps,
    config: { damping: 16, stiffness: 130 },
  });
  const toastX = interpolate(toastSpring, [0, 1], [440, 0]);

  const titleSpring = spring({
    frame: frame - 6,
    fps,
    config: { damping: 18, stiffness: 100 },
  });

  const edgeGlow = 0.06 + Math.sin(frame / (fps * 3)) * 0.03;

  return (
    <AbsoluteFill style={{ background: primaryColor, overflow: "hidden" }}>
      <StyleLayerStack layers={styleLayers} />
      {/* Mint edge glow */}
      <AbsoluteFill
        style={{
          background: `radial-gradient(ellipse at 85% 15%, rgba(52,211,153,${edgeGlow * 1.5}) 0%, transparent 50%),
                       radial-gradient(ellipse at 15% 85%, rgba(52,211,153,${edgeGlow}) 0%, transparent 45%)`,
          pointerEvents: "none",
        }}
      />

      {/* Layout */}
      <AbsoluteFill style={{ display: "flex", flexDirection: "row", padding: 60 }}>
        {/* Sidebar */}
        <div
          style={{
            width: 200,
            display: "flex",
            flexDirection: "column",
            gap: 12,
            paddingTop: 48,
          }}
        >
          {sidebarItems.map((item, idx) => {
            const itemSpring = spring({
              frame: frame - idx * 5,
              fps,
              config: { damping: 16, stiffness: 120 },
            });
            const isActive = idx === 0;

            return (
              <div
                key={idx}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 14,
                  padding: "14px 16px",
                  borderRadius: 12,
                  background: isActive ? `rgba(52,211,153,0.14)` : "transparent",
                  opacity: itemSpring,
                  transform: `translateX(${interpolate(itemSpring, [0, 1], [-50, 0])}px)`,
                  willChange: "transform, opacity",
                }}
              >
                <div
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    background: isActive ? accentColor : "rgba(255,255,255,0.28)",
                    boxShadow: isActive ? `0 0 8px ${accentColor}` : "none",
                    flexShrink: 0,
                  }}
                />
                <span
                  style={{
                    fontSize: 22,
                    fontWeight: isActive ? 600 : 400,
                    color: isActive ? accentColor : "rgba(255,255,255,0.55)",
                    fontFamily: "Inter, system-ui, sans-serif",
                  }}
                >
                  {item}
                </span>
              </div>
            );
          })}
        </div>

        {/* Main content panel */}
        <div style={{ flex: 1, marginLeft: 44 }}>
          <div
            style={{
              fontSize: 34,
              fontWeight: 700,
              color: "#FFFFFF",
              fontFamily: "Inter, system-ui, sans-serif",
              opacity: titleSpring,
              transform: `translateY(${interpolate(titleSpring, [0, 1], [18, 0])}px)`,
              marginBottom: 24,
              paddingTop: 48,
              willChange: "transform, opacity",
            }}
          >
            {panelTitle}
          </div>

          {DEFAULT_TASKS.map((task, idx) => {
            const cardSpring = spring({
              frame: frame - (14 + idx * 8),
              fps,
              config: { damping: 18, stiffness: 100 },
            });

            return (
              <div
                key={idx}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 18,
                  padding: "20px 24px",
                  marginBottom: 12,
                  borderRadius: 12,
                  background: task.active
                    ? "rgba(52,211,153,0.1)"
                    : "rgba(255,255,255,0.05)",
                  borderLeft: task.active
                    ? `3px solid ${accentColor}`
                    : "3px solid transparent",
                  opacity: cardSpring,
                  transform: `scale(${interpolate(cardSpring, [0, 1], [0.94, 1])})`,
                  willChange: "transform, opacity",
                }}
              >
                <div
                  style={{
                    width: 24,
                    height: 24,
                    borderRadius: 6,
                    border: task.done
                      ? "none"
                      : "2px solid rgba(255,255,255,0.3)",
                    background: task.done ? accentColor : "transparent",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                  }}
                >
                  {task.done && (
                    <span style={{ color: "#000", fontSize: 14, fontWeight: 800, lineHeight: 1 }}>
                      ✓
                    </span>
                  )}
                </div>
                <span
                  style={{
                    fontSize: 21,
                    color: task.done ? "rgba(255,255,255,0.38)" : "#FFFFFF",
                    textDecoration: task.done ? "line-through" : "none",
                    fontFamily: "Inter, system-ui, sans-serif",
                  }}
                >
                  {task.label}
                </span>
              </div>
            );
          })}
        </div>
      </AbsoluteFill>

      {/* Toast notification */}
      <div
        style={{
          position: "absolute",
          top: 72,
          right: 60,
          transform: `translateX(${toastX}px)`,
          background: "rgba(255,255,255,0.95)",
          borderRadius: 14,
          padding: "16px 24px",
          borderLeft: `4px solid ${accentColor}`,
          boxShadow: "0 8px 32px rgba(0,0,0,0.45)",
          opacity: toastSpring,
          minWidth: 280,
          willChange: "transform, opacity",
        }}
      >
        <div
          style={{
            fontSize: 21,
            fontWeight: 600,
            color: primaryColor,
            fontFamily: "Inter, system-ui, sans-serif",
          }}
        >
          {toastText}
        </div>
      </div>
    </AbsoluteFill>
  );
};
