import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          base: "#070b14",
          panel: "#0d1424",
          card: "#111a2e",
          elevated: "#16213a",
        },
        accent: {
          DEFAULT: "#22d3ee",   // cyan
          glow: "#38bdf8",      // sky
          violet: "#8b5cf6",
          green: "#34d399",
          amber: "#fbbf24",
        },
        ink: {
          DEFAULT: "#e6edf7",
          dim: "#9fb0c8",
          faint: "#5f708a",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(34,211,238,0.25), 0 8px 30px rgba(34,211,238,0.12)",
        card: "0 10px 30px rgba(0,0,0,0.35)",
      },
      keyframes: {
        sweep: {
          "0%": { width: "0%" },
          "50%": { width: "85%" },
          "100%": { width: "100%" },
        },
        pulseDot: {
          "0%,100%": { opacity: "0.5", transform: "scale(0.8)" },
          "50%": { opacity: "1", transform: "scale(1.2)" },
        },
        floatUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        sweep: "sweep 2.5s ease-in-out infinite",
        pulseDot: "pulseDot 2s ease-in-out infinite",
        floatUp: "floatUp 0.3s ease-out",
      },
    },
  },
  plugins: [],
};
export default config;
