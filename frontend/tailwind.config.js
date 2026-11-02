/** @type {import('tailwindcss').Config} */
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`;
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        paper: v("paper"),
        surface: v("surface"),
        sunken: v("sunken"),
        ink: v("ink"),
        ink2: v("ink-2"),
        muted: v("muted"),
        line: v("line"),
        accent: v("accent"),
        "accent-ink": v("accent-ink"),
        teal: v("teal"),
        crit: v("crit"),
        high: v("high"),
        med: v("med"),
        low: v("low"),
        good: v("good"),
      },
      fontFamily: {
        display: ['"Fraunces Variable"', "Georgia", "serif"],
        sans: ['"IBM Plex Sans"', "system-ui", "-apple-system", '"Segoe UI"', "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
      },
      boxShadow: {
        card: "0 1px 0 rgb(var(--line) / 1), 0 1px 2px rgb(0 0 0 / 0.04)",
        lift: "0 10px 30px -12px rgb(0 0 0 / 0.25)",
      },
    },
  },
  plugins: [],
};
