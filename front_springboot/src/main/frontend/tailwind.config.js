/** @type {import('tailwindcss').Config} */
module.exports = {
  // Los .js de static/ arman HTML con clases de Tailwind: si no se escanean,
  // esas clases no llegan a main.css.
  content: [
    "../resources/templates/**/*.html",
    "../resources/static/*.js",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      // Azul Austral Lens. DEFAULT (#0064AF) da 6:1 sobre blanco; el azul
      // claro original (#007DC8) no llega a 4.5:1 en texto pequeño.
      colors: {
        brand: {
          50: "#e8f4fd",
          100: "#d0eaf8",
          DEFAULT: "#0064AF",
          dark: "#004B96",
          ink: "#003B75",
        },
      },
    },
  },
  plugins: [],
}
