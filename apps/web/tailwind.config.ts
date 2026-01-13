import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          primary: "#00A878",
          accent: "#FF7A48",
        },
      },
    },
  },
  plugins: [],
};

export default config;
