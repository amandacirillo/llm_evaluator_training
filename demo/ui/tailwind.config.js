/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // App palette (from the build spec).
        bg: "#FAFAFB",
        surface: "#FFFFFF",
        ink: "#1B2A4A",
        "ink-muted": "#6B7280",
        border: "#E4E6EB",
        accent: "#9AA6EF",
        "accent-strong": "#7C8AE8",
        "accent-soft": "#E8EAFB",
        pass: "#2F8F5B",
        fail: "#C24B3A",
      },
      borderRadius: {
        DEFAULT: "10px",
        pill: "999px",
      },
      fontFamily: {
        sans: [
          "Inter",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};
