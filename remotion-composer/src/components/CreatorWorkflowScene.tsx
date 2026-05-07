import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { MacbookMotionRig } from "./MacbookMotionRig";
import { ProductImageMotion } from "./ProductImageMotion";
import { StyleLayerStack, type StyleLayerConfig } from "./StyleLayers";

export interface CreatorWorkflowSceneProps {
  mode?: "opening" | "workflow";
  productImage?: string;
  hardwareTreatment?: "synthetic_laptop";
  title?: string;
  subtitle?: string;
  labels?: string[];
  workflowItems?: string[];
  accentColor?: string;
  backgroundColor?: string;
  sceneDurationSeconds?: number;
  styleLayers?: StyleLayerConfig[];
}

const DEFAULT_LABELS = ["Edit", "Design", "Code", "AI", "Preview"];
const DEFAULT_WORKFLOW = ["Timeline", "Color", "Code", "AI Assist", "Export"];
const CHIP_POSITIONS = [
  { left: "9%", top: "24%" },
  { left: "28%", top: "68%" },
  { left: "47%", top: "20%" },
  { left: "57%", top: "70%" },
  { left: "50%", top: "48%" },
];

const ProgressRail: React.FC<{
  label: string;
  delay: number;
  accentColor: string;
}> = ({ label, delay, accentColor }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const enter = spring({
    frame: frame - delay,
    fps,
    config: { damping: 17, stiffness: 120 },
  });
  const fill = interpolate(frame - delay, [10, 85], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        opacity: enter,
        transform: `translateY(${interpolate(enter, [0, 1], [26, 0])}px)`,
        width: 280,
        padding: "16px 18px",
        borderRadius: 16,
        background: "rgba(255,255,255,0.075)",
        border: "1px solid rgba(255,255,255,0.12)",
        boxShadow: "0 18px 48px rgba(0,0,0,0.25)",
        willChange: "transform, opacity",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginBottom: 12,
          color: "rgba(255,255,255,0.82)",
          fontFamily: "Inter, system-ui, sans-serif",
          fontSize: 18,
          fontWeight: 650,
        }}
      >
        <span>{label}</span>
        <span style={{ color: accentColor }}>{Math.round(fill * 100)}%</span>
      </div>
      <div
        style={{
          height: 8,
          borderRadius: 999,
          background: "rgba(255,255,255,0.1)",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${fill * 100}%`,
            background: `linear-gradient(90deg, ${accentColor}, #FFFFFF)`,
            borderRadius: 999,
            boxShadow: `0 0 18px ${accentColor}88`,
          }}
        />
      </div>
    </div>
  );
};

const FloatingChip: React.FC<{
  label: string;
  index: number;
  accentColor: string;
}> = ({ label, index, accentColor }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const enter = spring({
    frame: frame - 12 - index * 5,
    fps,
    config: { damping: 14, stiffness: 140 },
  });
  const driftX = Math.sin(frame / (fps * 1.2) + index) * 16;
  const driftY = Math.cos(frame / (fps * 1.6) + index) * 10;

  return (
    <div
      style={{
        position: "absolute",
        left: CHIP_POSITIONS[index % CHIP_POSITIONS.length].left,
        top: CHIP_POSITIONS[index % CHIP_POSITIONS.length].top,
        transform: `translate(${driftX}px, ${driftY}px) scale(${interpolate(enter, [0, 1], [0.75, 1])})`,
        opacity: enter,
        padding: "13px 18px",
        borderRadius: 999,
        background: "rgba(255,255,255,0.1)",
        border: `1px solid ${accentColor}66`,
        color: "#FFFFFF",
        fontFamily: "Inter, system-ui, sans-serif",
        fontSize: 20,
        fontWeight: 700,
        boxShadow: `0 0 28px ${accentColor}22`,
        willChange: "transform, opacity",
      }}
    >
      {label}
    </div>
  );
};

export const CreatorWorkflowScene: React.FC<CreatorWorkflowSceneProps> = ({
  mode = "opening",
  productImage,
  hardwareTreatment,
  title = "A blank timeline wakes up.",
  subtitle = "Every creative thread starts moving.",
  labels = DEFAULT_LABELS,
  workflowItems = DEFAULT_WORKFLOW,
  accentColor = "#A7C7E7",
  backgroundColor = "#050505",
  sceneDurationSeconds,
  styleLayers,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const totalFrames = sceneDurationSeconds ? Math.round(sceneDurationSeconds * fps) : durationInFrames;
  const hasProductImage = Boolean(productImage?.trim());
  const showSyntheticHardware = !hasProductImage && hardwareTreatment === "synthetic_laptop";

  const productEnter = spring({
    frame: frame - 4,
    fps,
    config: { damping: 18, stiffness: 95, mass: 0.9 },
  });
  const productScale = mode === "opening"
    ? interpolate(productEnter, [0, 1], [0.82, 1.0])
    : interpolate(productEnter, [0, 1], [0.72, 0.88]);
  const productX = mode === "opening"
    ? interpolate(productEnter, [0, 1], [0, -230])
    : interpolate(productEnter, [0, 1], [0, -420]);
  const productY = Math.sin(frame / (fps * 1.7)) * 5;

  const playhead = interpolate(frame, [0, totalFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const lightSweep = interpolate(frame, [0, totalFrames * 0.55], [-40, 140], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const titleSpring = spring({
    frame: frame - 16,
    fps,
    config: { damping: 19, stiffness: 90 },
  });
  const cursorVisible = Math.floor(frame / 16) % 2 === 0;

  return (
    <AbsoluteFill style={{ background: backgroundColor, overflow: "hidden" }}>
      <StyleLayerStack layers={styleLayers} />
      <AbsoluteFill
        style={{
          background: `
            radial-gradient(ellipse at 32% 42%, ${accentColor}22 0%, transparent 38%),
            radial-gradient(ellipse at 84% 18%, rgba(255,255,255,0.1) 0%, transparent 28%)
          `,
        }}
      />
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: `linear-gradient(112deg, transparent ${lightSweep - 18}%, rgba(255,255,255,0.13) ${lightSweep}%, transparent ${lightSweep + 18}%)`,
          mixBlendMode: "screen",
        }}
      />

      {hasProductImage && productImage ? (
        <ProductImageMotion
          src={productImage}
          variant={mode === "opening" ? "opening" : "workflow"}
          accentColor={accentColor}
          x={productX}
          y={productY}
          scale={productScale}
        />
      ) : showSyntheticHardware ? (
        <MacbookMotionRig
          variant={mode === "opening" ? "opening" : "workflow"}
          accentColor={accentColor}
          x={productX}
          y={productY}
          scale={productScale}
        />
      ) : null}

      <div
        style={{
          position: "absolute",
          right: 118,
          top: mode === "opening" ? 144 : 92,
          width: mode === "opening" ? 580 : 720,
          opacity: titleSpring,
          transform: `translateY(${interpolate(titleSpring, [0, 1], [30, 0])}px)`,
          willChange: "transform, opacity",
        }}
      >
        <div
          style={{
            color: "#FFFFFF",
            fontFamily: "Inter, system-ui, sans-serif",
            fontSize: mode === "opening" ? 64 : 52,
            fontWeight: 820,
            lineHeight: 1.02,
            letterSpacing: 0,
            marginBottom: 18,
          }}
        >
          {title}
        </div>
        <div
          style={{
            color: "rgba(255,255,255,0.72)",
            fontFamily: "Inter, system-ui, sans-serif",
            fontSize: 26,
            lineHeight: 1.32,
          }}
        >
          {subtitle}
        </div>
      </div>

      {mode === "opening" ? (
        <>
          {labels.slice(0, 5).map((label, index) => (
            <FloatingChip key={label} label={label} index={index} accentColor={accentColor} />
          ))}
          <div
            style={{
              position: "absolute",
              left: 150,
              right: 150,
              bottom: 112,
              height: 104,
              borderRadius: 22,
              background: "rgba(255,255,255,0.075)",
              border: "1px solid rgba(255,255,255,0.12)",
              boxShadow: "0 24px 80px rgba(0,0,0,0.35)",
              overflow: "hidden",
            }}
          >
            <div style={{ position: "absolute", left: 28, right: 28, top: 22, display: "flex", gap: 10 }}>
              {labels.slice(0, 5).map((label, index) => {
                const clipSpring = spring({
                  frame: frame - 20 - index * 6,
                  fps,
                  config: { damping: 14, stiffness: 140 },
                });
                return (
                  <div
                    key={label}
                    style={{
                      flex: 1,
                      height: 58,
                      borderRadius: 12,
                      background: index % 2 === 0 ? `${accentColor}30` : "rgba(255,255,255,0.12)",
                      opacity: clipSpring,
                      transform: `scaleX(${clipSpring})`,
                      transformOrigin: "left center",
                    }}
                  />
                );
              })}
            </div>
            <div
              style={{
                position: "absolute",
                top: 12,
                bottom: 12,
                left: `${4 + playhead * 88}%`,
                width: 3,
                borderRadius: 3,
                background: "#FFFFFF",
                boxShadow: "0 0 20px #FFFFFF",
              }}
            />
          </div>
        </>
      ) : (
        <>
          <div
            style={{
              position: "absolute",
              right: 128,
              top: 250,
              width: 356,
              padding: "17px 20px",
              borderRadius: 18,
              background: "rgba(255,255,255,0.085)",
              border: `1px solid ${accentColor}55`,
              color: "rgba(255,255,255,0.88)",
              fontFamily: "Inter, system-ui, sans-serif",
              fontSize: 22,
              fontWeight: 650,
              letterSpacing: 0,
              boxShadow: `0 18px 44px ${accentColor}20`,
            }}
          >
            Refine direction
            <span
              style={{
                display: "inline-block",
                width: 3,
                height: 24,
                marginLeft: 8,
                verticalAlign: "-4px",
                borderRadius: 2,
                background: accentColor,
                opacity: cursorVisible ? 1 : 0,
              }}
            />
          </div>
          <div
            style={{
              position: "absolute",
              right: 110,
              bottom: 106,
              display: "grid",
              gridTemplateColumns: "repeat(2, 280px)",
              gap: 20,
            }}
          >
            {workflowItems.slice(0, 4).map((item, index) => (
              <ProgressRail key={item} label={item} delay={18 + index * 8} accentColor={accentColor} />
            ))}
          </div>
          <svg
            width="1920"
            height="1080"
            style={{
              position: "absolute",
              inset: 0,
              pointerEvents: "none",
              opacity: 0.7,
            }}
          >
            {[0, 1, 2].map((i) => {
              const line = interpolate(frame - 22 - i * 8, [0, 42], [0, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              });
              const length = 470 + i * 42;
              return (
                <path
                  key={i}
                  d={`M760 ${390 + i * 78} C980 ${280 + i * 48}, 1110 ${470 + i * 64}, ${1270 + i * 20} ${610 + i * 82}`}
                  stroke={accentColor}
                  strokeWidth="2.5"
                  strokeDasharray={length}
                  strokeDashoffset={length * (1 - line)}
                  fill="none"
                  opacity={0.42 + i * 0.12}
                />
              );
            })}
          </svg>
        </>
      )}
    </AbsoluteFill>
  );
};
