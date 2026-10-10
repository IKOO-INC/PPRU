/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/templates/**/*.html",
    "./app/static/js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        // Hijau pesantren (emerald) — nilai sama dengan build referensi
        primary: {
          50: "#ecfdf5", 100: "#d1fae5", 200: "#a7f3d0", 300: "#6ee7b7",
          400: "#34d399", 500: "#10b981", 600: "#059669", 700: "#047857",
          800: "#065f46", 900: "#064e3b",
        },
        // Emas/amber untuk aksen (CTA, badge)
        accent: {
          DEFAULT: "#d97706",
          dark: "#b45309",
          light: "#fbbf24",
        },
      },
      fontFamily: {
        sans: ["Outfit", "sans-serif"],
        arabic: ["Amiri", "serif"],
      },
      boxShadow: {
        card: "0 10px 30px -10px rgba(0,0,0,.08)",
        glow: "0 0 30px rgba(16,185,129,.2)",
      },
    },
  },
  plugins: [],
};
