import {
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

export interface MacbookMotionRigProps {
  variant?: "opening" | "workflow" | "hero";
  accentColor?: string;
  scale?: number;
  x?: number;
  y?: number;
}

const SCREEN_LINES = [
  "#A7C7E7",
  "#FFFFFF",
  "#7DD3FC",
  "#F5F5F7",
  "#A7C7E7",
];

export const MacbookMotionRig: React.FC<MacbookMotionRigProps> = ({
  variant = "opening",
  accentColor = "#A7C7E7",
  scale = 1,
  x = 0,
  y = 0,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const entrance = spring({
    frame: frame - 2,
    fps,
    config: { damping: 18, stiffness: 96, mass: 0.9 },
  });
  const lid = spring({
    frame: frame - (variant === "hero" ? 5 : 10),
    fps,
    config: { damping: 16, stiffness: 82, mass: 0.92 },
  });

  const orbit = Math.sin(frame / (fps * 2.3));
  const hover = Math.cos(frame / (fps * 1.7)) * 7;
  const yaw = variant === "workflow" ? -10 + orbit * 3 : variant === "hero" ? orbit * 2 : -6 + orbit * 2.5;
  const rigScale = scale * interpolate(entrance, [0, 1], [0.72, 1]);
  const lidAngle = interpolate(lid, [0, 1], [-64, -9], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const cursor = interpolate(frame % Math.round(fps * 2.2), [0, fps * 2.2], [7, 93], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const sweep = interpolate(frame % Math.round(fps * 2.8), [0, fps * 2.8], [-35, 135], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        position: "absolute",
        left: "50%",
        top: variant === "hero" ? 64 + y : 196 + y,
        width: 780,
        height: 450,
        transform: `translateX(calc(-50% + ${x}px)) translateY(${hover}px) scale(${rigScale}) rotateY(${yaw}deg)`,
        transformStyle: "preserve-3d",
        perspective: 1300,
        opacity: entrance,
        willChange: "transform, opacity",
      }}
    >
      <div
        style={{
          position: "absolute",
          left: 82,
          bottom: 52,
          width: 616,
          height: 350,
          borderRadius: 30,
          background: "linear-gradient(135deg, #1F2329 0%, #090B0F 54%, #272B31 100%)",
          border: "2px solid rgba(255,255,255,0.19)",
          boxShadow: `0 42px 120px rgba(0,0,0,0.58), 0 0 110px ${accentColor}22`,
          overflow: "hidden",
          transformOrigin: "bottom center",
          transform: `rotateX(${lidAngle}deg) translateZ(22px)`,
          willChange: "transform",
        }}
      >
        <div
          style={{
            position: "absolute",
            inset: 18,
            borderRadius: 22,
            background: "linear-gradient(155deg, #080B11 0%, #101722 52%, #05070A 100%)",
            overflow: "hidden",
            border: "1px solid rgba(255,255,255,0.09)",
          }}
        >
          <div
            style={{
              position: "absolute",
              left: 22,
              top: 20,
              right: 22,
              height: 32,
              borderRadius: 10,
              background: "rgba(255,255,255,0.055)",
              display: "flex",
              alignItems: "center",
              gap: 8,
              paddingLeft: 14,
            }}
          >
            {[0, 1, 2].map((dot) => (
              <span
                key={dot}
                style={{
                  width: 9,
                  height: 9,
                  borderRadius: 999,
                  background: dot === 0 ? "#FF5F57" : dot === 1 ? "#FFBD2E" : "#28C840",
                  opacity: 0.86,
                }}
              />
            ))}
          </div>

          <div
            style={{
              position: "absolute",
              left: 30,
              top: 76,
              width: 170,
              bottom: 28,
              borderRadius: 18,
              background: "rgba(255,255,255,0.055)",
              border: "1px solid rgba(255,255,255,0.07)",
              padding: 18,
            }}
          >
            {[0, 1, 2, 3].map((item) => {
              const active = interpolate(frame - item * 10, [0, 18], [0, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              });
              return (
                <div
                  key={item}
                  style={{
                    height: 22,
                    width: `${62 + item * 8}%`,
                    marginBottom: 18,
                    borderRadius: 7,
                    background: item === 1 ? `${accentColor}${Math.round(72 + active * 72).toString(16)}` : "rgba(255,255,255,0.18)",
                    transform: `translateX(${interpolate(active, [0, 1], [-14, 0])}px)`,
                    opacity: 0.45 + active * 0.55,
                  }}
                />
              );
            })}
          </div>

          <div
            style={{
              position: "absolute",
              left: 226,
              top: 78,
              right: 30,
              height: 126,
              borderRadius: 20,
              background: "rgba(255,255,255,0.065)",
              border: `1px solid ${accentColor}44`,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                position: "absolute",
                left: 18,
                right: 18,
                bottom: 18,
                height: 54,
                display: "grid",
                gridTemplateColumns: "repeat(5, 1fr)",
                gap: 9,
                alignItems: "end",
              }}
            >
              {SCREEN_LINES.map((color, index) => {
                const level = 18 + ((frame * (index + 2)) % 72);
                return (
                  <div
                    key={`${color}-${index}`}
                    style={{
                      height: level,
                      borderRadius: 6,
                      background: color,
                      opacity: 0.38 + index * 0.1,
                      boxShadow: `0 0 18px ${color}33`,
                    }}
                  />
                );
              })}
            </div>
            <div
              style={{
                position: "absolute",
                left: `${cursor}%`,
                top: 16,
                bottom: 14,
                width: 3,
                borderRadius: 6,
                background: "#FFFFFF",
                boxShadow: "0 0 18px rgba(255,255,255,0.9)",
              }}
            />
          </div>

          <div
            style={{
              position: "absolute",
              left: 226,
              right: 30,
              bottom: 28,
              height: 78,
              borderRadius: 18,
              background: "rgba(255,255,255,0.045)",
              border: "1px solid rgba(255,255,255,0.07)",
              overflow: "hidden",
            }}
          >
            {[0, 1, 2].map((track) => (
              <div
                key={track}
                style={{
                  position: "absolute",
                  left: 18,
                  top: 14 + track * 20,
                  width: `${42 + ((frame * (track + 1)) % 38)}%`,
                  height: 10,
                  borderRadius: 10,
                  background: track === 1 ? accentColor : "rgba(255,255,255,0.22)",
                  opacity: track === 1 ? 0.78 : 0.5,
                }}
              />
            ))}
          </div>

          <div
            style={{
              position: "absolute",
              inset: 0,
              background: `linear-gradient(112deg, transparent ${sweep - 16}%, rgba(255,255,255,0.18) ${sweep}%, transparent ${sweep + 16}%)`,
              mixBlendMode: "screen",
            }}
          />
        </div>
      </div>

      <div
        style={{
          position: "absolute",
          left: 44,
          bottom: 18,
          width: 694,
          height: 172,
          borderRadius: "28px 28px 44px 44px",
          background: "linear-gradient(180deg, #D2D7DD 0%, #7F878F 48%, #2F3338 100%)",
          transform: "rotateX(64deg) translateZ(-5px)",
          transformOrigin: "center top",
          boxShadow: "0 44px 96px rgba(0,0,0,0.55)",
          overflow: "hidden",
          border: "1px solid rgba(255,255,255,0.35)",
        }}
      >
        <div
          style={{
            position: "absolute",
            left: 240,
            top: 30,
            width: 214,
            height: 54,
            borderRadius: 16,
            background: "rgba(0,0,0,0.2)",
            border: "1px solid rgba(255,255,255,0.18)",
          }}
        />
        {[0, 1, 2, 3].map((row) => (
          <div
            key={row}
            style={{
              position: "absolute",
              left: 86 + row * 7,
              right: 86 + row * 7,
              top: 20 + row * 21,
              display: "grid",
              gridTemplateColumns: "repeat(12, 1fr)",
              gap: 7,
              opacity: 0.36,
            }}
          >
            {Array.from({ length: 12 }).map((_, key) => (
              <div
                key={key}
                style={{
                  height: 11,
                  borderRadius: 4,
                  background: "rgba(255,255,255,0.55)",
                }}
              />
            ))}
          </div>
        ))}
      </div>

      <div
        style={{
          position: "absolute",
          left: 78,
          right: 78,
          bottom: -10,
          height: 44,
          borderRadius: "50%",
          background: `radial-gradient(ellipse at center, ${accentColor}33 0%, rgba(0,0,0,0.48) 46%, transparent 72%)`,
          filter: "blur(10px)",
          opacity: 0.86,
        }}
      />
    </div>
  );
};
