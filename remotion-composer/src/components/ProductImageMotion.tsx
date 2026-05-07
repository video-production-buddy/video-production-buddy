import {
  Img,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { resolveAsset } from "../assetPath";

export type ProductImageMotionVariant = "opening" | "workflow" | "brand";

export interface ProductImageMotionProps {
  src: string;
  variant?: ProductImageMotionVariant;
  accentColor?: string;
  scale?: number;
  x?: number;
  y?: number;
}

export const ProductImageMotion: React.FC<ProductImageMotionProps> = ({
  src,
  variant = "opening",
  accentColor = "#A7C7E7",
  scale = 1,
  x = 0,
  y = 0,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const entrance = spring({
    frame: frame - 4,
    fps,
    config: { damping: 18, stiffness: 95, mass: 0.9 },
  });
  const imageScale = scale * interpolate(entrance, [0, 1], [0.82, 1]);
  const hover = Math.cos(frame / (fps * 1.7)) * (variant === "brand" ? 3 : 6);
  const yaw = variant === "workflow"
    ? -6 + Math.sin(frame / (fps * 2.4)) * 2
    : Math.sin(frame / (fps * 2.6)) * 1.5;

  const dimensions = variant === "brand"
    ? { width: 820, height: 250, top: 0, padding: 18, radius: 30 }
    : { width: 760, height: 430, top: variant === "workflow" ? 150 : 170, padding: 34, radius: 36 };

  return (
    <div
      style={{
        position: "absolute",
        left: "50%",
        top: dimensions.top + y,
        width: dimensions.width,
        height: dimensions.height,
        transform: `translateX(calc(-50% + ${x}px)) translateY(${hover}px) scale(${imageScale}) rotateY(${yaw}deg)`,
        transformStyle: "preserve-3d",
        perspective: 1200,
        opacity: entrance,
        willChange: "transform, opacity",
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: dimensions.padding,
          borderRadius: dimensions.radius,
          background: `radial-gradient(ellipse at center, ${accentColor}22 0%, rgba(255,255,255,0.045) 48%, transparent 76%)`,
          border: "1px solid rgba(255,255,255,0.13)",
          boxShadow: `0 42px 120px rgba(0,0,0,0.42), 0 0 100px ${accentColor}22`,
          overflow: "hidden",
        }}
      >
        <Img
          src={resolveAsset(src)}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "contain",
            filter: "drop-shadow(0 26px 42px rgba(0,0,0,0.42))",
          }}
        />
        <div
          style={{
            position: "absolute",
            inset: 0,
            background: `linear-gradient(112deg, transparent 22%, rgba(255,255,255,0.13) 48%, transparent 72%)`,
            mixBlendMode: "screen",
            opacity: interpolate(frame % Math.round(fps * 2.8), [0, fps * 2.8], [0.15, 0.55], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            }),
          }}
        />
      </div>
      <div
        style={{
          position: "absolute",
          left: 88,
          right: 88,
          bottom: -18,
          height: 42,
          borderRadius: "50%",
          background: `radial-gradient(ellipse at center, ${accentColor}33 0%, rgba(0,0,0,0.5) 48%, transparent 72%)`,
          filter: "blur(11px)",
          opacity: 0.78,
        }}
      />
    </div>
  );
};
