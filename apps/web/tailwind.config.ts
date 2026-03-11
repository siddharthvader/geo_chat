import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#f5efe4",
        ink: "#1f1c17",
        accent: "#a24b2a",
        mist: "#d8d2c3",
        pine: "#29595b",
      },
      boxShadow: {
        panel: "0 16px 40px rgba(31, 28, 23, 0.14)",
      },
    },
  },
  plugins: [],
};

export default config;
