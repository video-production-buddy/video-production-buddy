import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { StyleLayerStack, type StyleLayerConfig } from "./StyleLayers";

export interface BrowserTabsSceneProps {
  tabCount?: number;
  showKeyboardPill?: boolean;
  keyShortcut?: string;
  backgroundColor?: string;
  sceneDurationSeconds?: number;
  styleLayers?: StyleLayerConfig[];
}

const TAB_LABELS = [
  "Project Br...",
  "Inbox (14)...",
  "Sprint Boa...",
  "Meeting No...",
  "Client Brief",
  "Q1 Plan...",
  "Roadmap...",
  "Slack #eng",
  "Linear is...",
  "Doc — sp...",
  "Async stand...",
  "Notion home",
];

// Implements: tab_overflow, cursor_blink, keyboard_pill, tab_close_slide
export const BrowserTabsScene: React.FC<BrowserTabsSceneProps> = ({
  tabCount = 9,
  showKeyboardPill = false,
  keyShortcut = "⌘ W",
  backgroundColor = "#0F1115",
  sceneDurationSeconds,
  styleLayers,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames, width } = useVideoConfig();
  const totalFrames = sceneDurationSeconds
    ? Math.round(sceneDurationSeconds * fps)
    : durationInFrames;

  const safeTabCount = Math.max(0, Math.floor(tabCount));
  const visibleTabs = Math.min(safeTabCount, TAB_LABELS.length);
  const hiddenTabCount = Math.max(0, safeTabCount - visibleTabs);

  // Sentinel: a very large but finite frame number when the keyboard pill is off,
  // so interpolate() never sees Infinity.
  const closeStart = showKeyboardPill ? Math.round(fps * 1.2) : 1_000_000;
  const closeEnd = closeStart + Math.round(fps * 0.25);
  const closeProgress = showKeyboardPill
    ? interpolate(frame, [closeStart, closeEnd], [0, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      })
    : 0;

  const fanStart = closeEnd;

  const pushIn = interpolate(frame, [0, totalFrames], [1.0, 1.03], {
    extrapolateRight: "clamp",
  });

  const cursorOn = Math.floor(frame / 16) % 2 === 0;

  const pillStart = Math.round(fps * 0.5);
  const pillFadeInEnd = pillStart + Math.round(fps * 0.1);
  const pillHoldEnd = pillFadeInEnd + Math.round(fps * 0.5);
  const pillFadeOutEnd = pillHoldEnd + Math.round(fps * 0.2);
  const pillOpacity = showKeyboardPill
    ? interpolate(
        frame,
        [pillStart, pillFadeInEnd, pillHoldEnd, pillFadeOutEnd],
        [0, 1, 1, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
      )
    : 0;

  const tabBarHeight = 64;
  const tabWidth = Math.floor((width - 200) / Math.max(visibleTabs, 6));

  return (
    <AbsoluteFill
      style={{
        background: backgroundColor,
        transform: `scale(${pushIn})`,
        transformOrigin: "center center",
        willChange: "transform",
      }}
    >
      <StyleLayerStack layers={styleLayers} />

      <div
        style={{
          position: "absolute",
          top: 80,
          left: 60,
          right: 60,
          bottom: 200,
          background: "#1B1F27",
          borderRadius: 18,
          overflow: "hidden",
          boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div
          style={{
            height: tabBarHeight,
            background: "#0E1116",
            display: "flex",
            alignItems: "center",
            padding: "8px 14px",
            gap: 6,
            borderBottom: "1px solid rgba(255,255,255,0.05)",
            overflow: "hidden",
          }}
        >
          {Array.from({ length: visibleTabs }).map((_, i) => {
            const isFirst = i === 0;
            const slideOut = isFirst ? closeProgress : 0;
            const fanSpring = spring({
              frame: frame - fanStart - i * Math.round(fps * 0.04),
              fps,
              config: { damping: 18, stiffness: 200 },
            });
            const fanScale = showKeyboardPill ? interpolate(fanSpring, [0, 1], [0.95, 1.0]) : 1;
            return (
              <div
                key={i}
                style={{
                  flex: 1,
                  minWidth: tabWidth * 0.6,
                  maxWidth: tabWidth,
                  height: 38,
                  background: i === 1 && showKeyboardPill ? "#272C36" : "#1B1F27",
                  border: "1px solid rgba(255,255,255,0.07)",
                  borderBottom: "none",
                  borderRadius: "8px 8px 0 0",
                  display: "flex",
                  alignItems: "center",
                  paddingLeft: 10,
                  paddingRight: 8,
                  gap: 8,
                  fontSize: 13,
                  color: "rgba(255,255,255,0.55)",
                  fontFamily: "Inter, system-ui, sans-serif",
                  transform: isFirst
                    ? `translateX(${slideOut * 200}px) scale(${1 - slideOut * 0.4})`
                    : `scale(${fanScale})`,
                  opacity: isFirst ? 1 - slideOut : 1,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  willChange: "transform, opacity",
                }}
              >
                <div
                  style={{
                    width: 12,
                    height: 12,
                    borderRadius: 3,
                    background: ["#586374", "#465062", "#566273", "#3D4453", "#5E6A7E"][i % 5],
                    flexShrink: 0,
                  }}
                />
                <span
                  style={{
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {TAB_LABELS[i % TAB_LABELS.length]}
                </span>
                {i % 3 === 0 && (
                  <span
                    style={{
                      fontSize: 10,
                      background: "#FF3B30",
                      color: "#fff",
                      borderRadius: 8,
                      padding: "1px 6px",
                      marginLeft: "auto",
                    }}
                  >
                    {3 + ((i * 7) % 17)}
                  </span>
                )}
              </div>
            );
          })}
          {hiddenTabCount > 0 && (
            <div
              style={{
                fontSize: 12,
                color: "rgba(255,255,255,0.45)",
                padding: "6px 10px",
                flexShrink: 0,
              }}
            >
              +{hiddenTabCount} more
            </div>
          )}
        </div>

        <div
          style={{
            flex: 1,
            padding: "60px 80px",
            color: "rgba(255,255,255,0.55)",
            fontFamily: "Inter, system-ui, sans-serif",
            fontSize: 22,
            lineHeight: 1.6,
          }}
        >
          <div style={{ opacity: 0.6 }}>Sprint planning — owner notes</div>
          <div style={{ marginTop: 16, opacity: 0.45 }}>
            ····················· · ······ ········ ········· ················
          </div>
          <div style={{ marginTop: 12, opacity: 0.45 }}>
            ······ ········· ····· ······· ··········· · ·······
          </div>
          <div style={{ marginTop: 28, opacity: 0.85 }}>
            — where was I?
            <span
              style={{
                display: "inline-block",
                width: 3,
                height: 26,
                background: "rgba(255,255,255,0.85)",
                marginLeft: 6,
                verticalAlign: "middle",
                opacity: cursorOn ? 1 : 0,
              }}
            />
          </div>
        </div>
      </div>

      {showKeyboardPill && (
        <div
          style={{
            position: "absolute",
            top: "45%",
            left: "50%",
            transform: "translate(-50%, -50%)",
            background: "rgba(20,22,28,0.92)",
            color: "#FFFFFF",
            padding: "16px 36px",
            borderRadius: 999,
            fontFamily: "Inter, system-ui, sans-serif",
            fontWeight: 600,
            fontSize: 36,
            letterSpacing: "0.05em",
            opacity: pillOpacity,
            boxShadow: "0 20px 50px rgba(0,0,0,0.5)",
            border: "1px solid rgba(255,255,255,0.1)",
            willChange: "opacity",
          }}
        >
          {keyShortcut}
        </div>
      )}
    </AbsoluteFill>
  );
};
