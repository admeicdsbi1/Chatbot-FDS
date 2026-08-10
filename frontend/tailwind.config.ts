import type { Config } from "tailwindcss";

/** Every colour resolves to a CSS custom property defined in globals.css, in
 *  the `rgb(var(--x) / <alpha-value>)` form so opacity modifiers still work
 *  (`border-line/20`, `bg-accent/10`). Swapping the theme swaps the tokens —
 *  no component needs a `dark:` variant. */
const token = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          base: token("bg-base"),
          panel: token("bg-panel"),
          card: token("bg-card"),
          elevated: token("bg-elevated"),
          sunken: token("bg-sunken"),
        },
        accent: {
          DEFAULT: token("accent"),
          glow: token("accent-glow"),
          violet: token("accent-violet"),
          green: token("accent-green"),
          amber: token("accent-amber"),
          red: token("accent-red"),
        },
        ink: {
          DEFAULT: token("ink"),
          dim: token("ink-dim"),
          faint: token("ink-faint"),
        },
        // Hairline colour: white in dark, ink in light. Always use with an
        // opacity modifier, e.g. `border-line/15`.
        line: token("line"),
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgb(var(--accent) / 0.25), 0 8px 30px rgb(var(--accent) / 0.12)",
        card: "0 10px 30px rgb(var(--shadow-rgb) / 0.12)",
        rail: "0 0 40px rgb(var(--shadow-rgb) / 0.25)",
      },
      maxWidth: {
        // The reading measure for technical prose. 672px (max-w-2xl) was tight
        // for the tables that make up most of this corpus.
        reading: "48rem",
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
