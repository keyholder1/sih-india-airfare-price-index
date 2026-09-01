import type { Config } from "tailwindcss";

/**
 * Design system for the Airfare Price Index dashboard.
 * Direction: statistical-intelligence platform — financial analytics +
 * aviation + government data. Light, editorial, number-forward.
 * Keep colour meanings consistent:
 *   rise  = airfares got MORE expensive (index up)
 *   fall  = airfares got cheaper (index down)
 *   synth = "this data is a demonstration / synthetic" marker only
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#F6F6F2",
        surface: "#FFFFFF",
        "surface-sunken": "#FBFBF8",
        hairline: "#E7E6DF",
        "hairline-strong": "#D9D8CF",
        ink: {
          DEFAULT: "#14161C",
          muted: "#565B66",
          faint: "#8B909B",
          inverse: "#F6F6F2",
        },
        brand: {
          DEFAULT: "#1B2E4E",
          deep: "#12213B",
          soft: "#24406E",
          wash: "#EEF1F6",
        },
        accent: {
          DEFAULT: "#2563EB",
          wash: "#E9F0FE",
        },
        rise: {
          DEFAULT: "#B23A2E",
          wash: "#FBECE9",
        },
        fall: {
          DEFAULT: "#0E7C6B",
          wash: "#E5F3F0",
        },
        synth: {
          DEFAULT: "#9A5B08",
          wash: "#FBF0DC",
          border: "#EBD6A8",
        },
        status: {
          ok: "#0E7C6B",
          insufficient: "#9A5B08",
          new: "#2563EB",
          discontinued: "#8B909B",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "SF Mono",
          "JetBrains Mono",
          "Cascadia Code",
          "Consolas",
          "Liberation Mono",
          "monospace",
        ],
      },
      fontSize: {
        "hero-num": ["4.25rem", { lineHeight: "1", letterSpacing: "-0.02em" }],
        "stat-num": ["2rem", { lineHeight: "1.05", letterSpacing: "-0.01em" }],
      },
      boxShadow: {
        panel: "0 1px 2px rgba(20, 22, 28, 0.04), 0 1px 12px rgba(20, 22, 28, 0.04)",
        "panel-hover": "0 2px 4px rgba(20, 22, 28, 0.06), 0 8px 28px rgba(20, 22, 28, 0.08)",
      },
      borderRadius: {
        panel: "14px",
      },
      transitionTimingFunction: {
        "out-soft": "cubic-bezier(0.16, 1, 0.3, 1)",
      },
      keyframes: {
        "fade-rise": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-rise": "fade-rise 0.5s cubic-bezier(0.16, 1, 0.3, 1) both",
      },
    },
  },
  plugins: [],
} satisfies Config;
