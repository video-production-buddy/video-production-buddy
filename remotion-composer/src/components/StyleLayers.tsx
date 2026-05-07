import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  random,
} from "remotion";

// ─── Discriminated-union config used by every dynamic-scene component ───
// Pass via `styleLayers?: StyleLayerConfig[]`. The order of the array IS the
// z-stack: index 0 renders furthest back; the last entry is on top of the
// scene's content (so put grain/vignette last for a finishing pass).

export type GrainBlendMode = "soft-light" | "overlay" | "multiply";
export type GlowPosition =
  | "center"
  | "top-left"
  | "top-right"
  | "bottom-left"
  | "bottom-right";
export type StyleParticleType = "dust" | "sparkle" | "fog";

export interface GrainConfig {
  type: "grain";
  intensity?: number;        // 0..1 (default 0.06)
  scale?: number;            // texture scale factor (default 1.5)
  blendMode?: GrainBlendMode; // default "soft-light"
}

export interface VignetteConfig {
  type: "vignette";
  strength?: number;         // 0..1 (default 0.25)
  color?: string;            // hex (default "#000000")
}

export interface AmbientGlowConfig {
  type: "ambient_glow";
  color: string;             // hex
  intensity?: number;        // 0..1 (default 0.35)
  position?: GlowPosition;   // default "center"
  radius?: number;           // 0..100 percent (default 60)
  pulse?: boolean;           // default false
}

export interface ParticleFieldConfig {
  type: "particle_field";
  count?: number;            // default 60
  particleType?: StyleParticleType; // default "dust"
  velocity?: number;         // default 0.4
  color?: string;            // default "#FFFFFF"
}

export interface LightRaysConfig {
  type: "light_rays";
  color: string;             // hex
  angle?: number;            // degrees, default 35
  count?: number;            // default 6
  intensity?: number;        // 0..1 (default 0.18)
}

export type StyleLayerConfig =
  | GrainConfig
  | VignetteConfig
  | AmbientGlowConfig
  | ParticleFieldConfig
  | LightRaysConfig;

// ─── Individual layer components ─────────────────────────────────────────

export const GrainOverlay: React.FC<GrainConfig> = ({
  intensity = 0.06,
  scale = 1.5,
  blendMode = "soft-light",
}) => {
  const frame = useCurrentFrame();
  const baseFrequency = 0.9 + ((frame % 6) * 0.02);
  const dataUri =
    `data:image/svg+xml;utf8,` +
    encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300">` +
      `<filter id="n"><feTurbulence type="fractalNoise" baseFrequency="${baseFrequency}" numOctaves="2" stitchTiles="stitch"/></filter>` +
      `<rect width="100%" height="100%" filter="url(#n)" opacity="${intensity}"/>` +
      `</svg>`
    );
  return (
    <AbsoluteFill
      style={{
        backgroundImage: `url("${dataUri}")`,
        backgroundRepeat: "repeat",
        backgroundSize: `${300 * scale}px ${300 * scale}px`,
        mixBlendMode: blendMode,
        opacity: 1,
        pointerEvents: "none",
      }}
    />
  );
};

export const VignetteOverlay: React.FC<VignetteConfig> = ({
  strength = 0.25,
  color = "#000000",
}) => {
  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(ellipse at center, transparent 50%, ${color} 100%)`,
        opacity: strength,
        pointerEvents: "none",
      }}
    />
  );
};

const positionToCSS: Record<GlowPosition, string> = {
  center: "50% 50%",
  "top-left": "20% 20%",
  "top-right": "80% 20%",
  "bottom-left": "20% 80%",
  "bottom-right": "80% 80%",
};

export const AmbientGlow: React.FC<AmbientGlowConfig> = ({
  color,
  intensity = 0.35,
  position = "center",
  radius = 60,
  pulse = false,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pulseOpacity = pulse
    ? intensity * (0.7 + Math.sin(frame / (fps * 1.4)) * 0.3)
    : intensity;
  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(ellipse at ${positionToCSS[position]}, ${color} 0%, transparent ${radius}%)`,
        opacity: pulseOpacity,
        pointerEvents: "none",
      }}
    />
  );
};

export const ParticleField: React.FC<ParticleFieldConfig> = ({
  count = 60,
  particleType = "dust",
  velocity = 0.4,
  color = "#FFFFFF",
}) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const particles = Array.from({ length: count }).map((_, i) => {
    const seedX = random(`px-${i}`) * width;
    const seedY = random(`py-${i}`) * height;
    const seedSize = random(`ps-${i}`);
    const seedDrift = random(`pd-${i}`);
    const drift = (frame / fps) * velocity * (0.5 + seedDrift);
    return { i, x: seedX, y: (seedY + drift * 30) % height, sz: seedSize };
  });

  if (particleType === "fog") {
    return (
      <AbsoluteFill style={{ pointerEvents: "none" }}>
        {particles.map((p) => (
          <div
            key={p.i}
            style={{
              position: "absolute",
              left: p.x,
              top: p.y,
              width: 200 + p.sz * 220,
              height: 200 + p.sz * 220,
              borderRadius: "50%",
              background: `radial-gradient(circle, ${color}22 0%, transparent 70%)`,
              opacity: 0.35,
            }}
          />
        ))}
      </AbsoluteFill>
    );
  }

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {particles.map((p) => {
        const r = particleType === "sparkle" ? 1 + p.sz * 3 : 1 + p.sz * 2;
        const op =
          particleType === "sparkle"
            ? 0.4 + 0.6 * Math.abs(Math.sin((frame + p.i * 5) / 12))
            : 0.18 + p.sz * 0.3;
        return (
          <div
            key={p.i}
            style={{
              position: "absolute",
              left: p.x,
              top: p.y,
              width: r * 2,
              height: r * 2,
              borderRadius: "50%",
              background: color,
              opacity: op,
              boxShadow: particleType === "sparkle" ? `0 0 ${r * 3}px ${color}` : undefined,
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

export const LightRays: React.FC<LightRaysConfig> = ({
  color,
  angle = 35,
  count = 6,
  intensity = 0.18,
}) => {
  const rays = Array.from({ length: count }).map((_, i) => (i / count) * 100);
  return (
    <AbsoluteFill style={{ pointerEvents: "none", overflow: "hidden" }}>
      <div
        style={{
          position: "absolute",
          top: "-50%",
          left: "-50%",
          width: "200%",
          height: "200%",
          background: rays
            .map(
              (o) =>
                `linear-gradient(${angle}deg, transparent ${o}%, ${color} ${o + 0.5}%, transparent ${o + 4}%)`
            )
            .join(", "),
          opacity: intensity,
        }}
      />
    </AbsoluteFill>
  );
};

// ─── Stack renderer ──────────────────────────────────────────────────────

export const StyleLayerStack: React.FC<{ layers?: StyleLayerConfig[] }> = ({
  layers,
}) => {
  if (!layers || layers.length === 0) return null;
  return (
    <>
      {layers.map((layer, idx) => {
        if (layer.type === "grain") return <GrainOverlay key={idx} {...layer} />;
        if (layer.type === "vignette") return <VignetteOverlay key={idx} {...layer} />;
        if (layer.type === "ambient_glow") return <AmbientGlow key={idx} {...layer} />;
        if (layer.type === "particle_field") return <ParticleField key={idx} {...layer} />;
        if (layer.type === "light_rays") return <LightRays key={idx} {...layer} />;
        return null;
      })}
    </>
  );
};
