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

export interface BrandCardSceneProps {
  brandName?: string;
  tagline?: string;
  ctaText?: string;
  productImage?: string;
  hardwareTreatment?: "synthetic_laptop";
  accentColor?: string;
  backgroundColor?: string;
  sceneDurationSeconds?: number;
  styleLayers?: StyleLayerConfig[];
}

export const BrandCardScene: React.FC<BrandCardSceneProps> = ({
  brandName = "FOCAL",
  tagline = "One screen. Zero chaos.",
  ctaText = "Find your focus at focal.app",
  productImage,
  hardwareTreatment,
  accentColor = "#34D399",
  backgroundColor = "#000000",
  sceneDurationSeconds,
  styleLayers,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const effectiveDuration = sceneDurationSeconds
    ? Math.round(sceneDurationSeconds * fps)
    : durationInFrames;
  void effectiveDuration;

  const hasProductImage = Boolean(productImage?.trim());
  const showSyntheticHardware = !hasProductImage && hardwareTreatment === "synthetic_laptop";

  const letters = brandName.split("");

  // Tagline fades in at 1.0s
  const taglineSpring = spring({
    frame: frame - Math.round(fps * 1.0),
    fps,
    config: { damping: 20, stiffness: 80 },
  });

  // CTA appears at 2.5s
  const ctaSpring = spring({
    frame: frame - Math.round(fps * 2.5),
    fps,
    config: { damping: 20, stiffness: 80 },
  });

  // Wordmark pulse at 4.0s: scale 1.0 → 1.03 → 1.0 over 0.6s
  const pulseStart = Math.round(fps * 4.0);
  const pulseMid = pulseStart + Math.round(fps * 0.3);
  const pulseEnd = pulseStart + Math.round(fps * 0.6);
  const wordmarkScale = interpolate(
    frame,
    [pulseStart, pulseMid, pulseEnd],
    [1.0, 1.03, 1.0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  // Underline draws in after all letters settle
  const underlineSpring = spring({
    frame: frame - letters.length * 2 - 4,
    fps,
    config: { damping: 15, stiffness: 60 },
  });

  return (
    <AbsoluteFill
      style={{
        background: backgroundColor,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexDirection: "column",
      }}
    >
      <StyleLayerStack layers={styleLayers} />
      {(hasProductImage || showSyntheticHardware) && (
        <div style={{ position: "relative", width: 820, height: 262, marginBottom: 30 }}>
          {hasProductImage && productImage ? (
            <ProductImageMotion
              src={productImage}
              variant="brand"
              accentColor={accentColor}
              scale={0.95}
              y={4}
            />
          ) : (
            <MacbookMotionRig variant="hero" accentColor={accentColor} scale={0.52} y={-18} />
          )}
        </div>
      )}
      {/* Wordmark */}
      <div
        style={{
          display: "flex",
          letterSpacing: 0,
          transform: `scale(${wordmarkScale})`,
          marginBottom: 8,
          willChange: "transform",
        }}
      >
        {letters.map((char, i) => {
          const letterSpring = spring({
            frame: frame - i * 2,
            fps,
            config: { damping: 14, stiffness: 160 },
          });
          return (
            <span
              key={i}
              style={{
                fontSize: 96,
                fontWeight: 600,
                color: "#FFFFFF",
                fontFamily: "Inter, 'Helvetica Neue', Arial, sans-serif",
                opacity: letterSpring,
                transform: `translateY(${interpolate(letterSpring, [0, 1], [40, 0])}px)`,
                display: "inline-block",
                willChange: "transform, opacity",
                whiteSpace: char === " " ? "pre" : undefined,
                minWidth: char === " " ? "0.28em" : undefined,
              }}
            >
              {char}
            </span>
          );
        })}
      </div>

      {/* Animated underline in accent color */}
      <div
        style={{
          height: 2,
          backgroundColor: accentColor,
          borderRadius: 1,
          width: interpolate(underlineSpring, [0, 1], [0, 340]),
          marginBottom: 36,
          opacity: underlineSpring,
        }}
      />

      {/* Tagline */}
      <div
        style={{
          fontSize: 34,
          fontWeight: 400,
          color: "rgba(255,255,255,0.82)",
          fontFamily: "Inter, system-ui, sans-serif",
          opacity: taglineSpring,
          transform: `translateY(${interpolate(taglineSpring, [0, 1], [20, 0])}px)`,
          marginBottom: 40,
          letterSpacing: 0,
          willChange: "transform, opacity",
        }}
      >
        {tagline}
      </div>

      {/* CTA in accent color */}
      <div
        style={{
          fontSize: 28,
          fontWeight: 500,
          color: accentColor,
          fontFamily: "Inter, system-ui, sans-serif",
          opacity: ctaSpring,
          transform: `translateY(${interpolate(ctaSpring, [0, 1], [16, 0])}px)`,
          letterSpacing: 0,
          willChange: "transform, opacity",
        }}
      >
        {ctaText}
      </div>
    </AbsoluteFill>
  );
};
