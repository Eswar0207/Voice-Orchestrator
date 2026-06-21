/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0B0E14",
        panel: "#11151F",
        line: "#1E2433",
        accent: {
          DEFAULT: "#6E9BFF",
          soft: "#8FB4FF",
        },
        signal: {
          pending: "#8A93A6",
          initiated: "#6E9BFF",
          qualified: "#3DD68C",
          notinterested: "#FF6B6B",
          failed: "#FF9F4A",
          review: "#F4C95D",
        },
      },
      fontFamily: {
        display: ["'Space Grotesk'", "system-ui", "sans-serif"],
        body: ["'Inter'", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "monospace"],
      },
      boxShadow: {
        glass: "0 8px 32px rgba(0, 0, 0, 0.35)",
      },
      backdropBlur: {
        xs: "2px",
      },
    },
  },
  plugins: [],
};
