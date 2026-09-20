/** Tailwind CSS configuration for LabelVerify institutional UI.
 * Architectural responsibility: map design tokens to utilities for the Treasury-inspired system.
 */
/** @type {import('tailwindcss').Config} */
import animate from "tailwindcss-animate";

export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        surface: "hsl(var(--surface))",
        foreground: "hsl(var(--foreground))",
        navy: "hsl(var(--navy))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary-blue))",
          foreground: "hsl(var(--primary-foreground))",
        },
        gold: "hsl(var(--accent-gold))",
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        pass: {
          DEFAULT: "hsl(var(--pass))",
          foreground: "hsl(var(--pass-foreground))",
          soft: "hsl(var(--pass-soft))",
        },
        review: {
          DEFAULT: "hsl(var(--review))",
          foreground: "hsl(var(--review-foreground))",
          soft: "hsl(var(--review-soft))",
        },
        fail: {
          DEFAULT: "hsl(var(--fail))",
          foreground: "hsl(var(--fail-foreground))",
          soft: "hsl(var(--fail-soft))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "var(--radius)",
        sm: "var(--radius)",
      },
      fontFamily: {
        sans: ['"Source Sans 3"', "Segoe UI", "system-ui", "sans-serif"],
        display: ['"Libre Franklin"', "Segoe UI", "system-ui", "sans-serif"],
      },
      maxWidth: {
        workspace: "80rem",
      },
    },
  },
  plugins: [animate],
};
