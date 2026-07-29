/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class', // We'll force dark mode by default on the body
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      colors: {
        background: '#09090b', // zinc-950
        surface: {
          DEFAULT: '#18181b', // zinc-900
          hover: '#27272a',   // zinc-800
          active: '#3f3f46',  // zinc-700
        },
        primary: {
          DEFAULT: '#6366f1', // indigo-500
          hover: '#4f46e5',   // indigo-600
          glow: 'rgba(99, 102, 241, 0.2)',
        },
        accent: {
          DEFAULT: '#8b5cf6', // violet-500
          hover: '#7c3aed',   // violet-600
        },
        danger: {
          DEFAULT: '#ef4444', // red-500
          hover: '#dc2626',   // red-600
          dim: 'rgba(239, 68, 68, 0.1)',
        },
        success: {
          DEFAULT: '#10b981', // emerald-500
          dim: 'rgba(16, 185, 129, 0.1)',
        },
        warning: {
          DEFAULT: '#f59e0b', // amber-500
          dim: 'rgba(245, 158, 11, 0.1)',
        },
        text: {
          primary: '#fafafa', // zinc-50
          secondary: '#a1a1aa', // zinc-400
          muted: '#71717a', // zinc-500
        },
        border: {
          DEFAULT: '#27272a', // zinc-800
          bright: '#3f3f46', // zinc-700
        },
      },
      boxShadow: {
        'card': '0 1px 3px 0 rgba(0, 0, 0, 0.4), 0 1px 2px -1px rgba(0, 0, 0, 0.3)',
        'dropdown': '0 10px 15px -3px rgba(0, 0, 0, 0.5), 0 4px 6px -4px rgba(0, 0, 0, 0.4)',
        'glow': '0 0 15px var(--tw-shadow-color)',
      },
      animation: {
        'pulse-slow': 'pulse 3s ease-in-out infinite',
        'slide-in': 'slideIn 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
        'fade-in': 'fadeIn 0.2s ease-out',
        'ticker': 'ticker 20s linear infinite',
      },
      keyframes: {
        slideIn: { from: { opacity: 0, transform: 'translateY(8px)' }, to: { opacity: 1, transform: 'translateY(0)' } },
        fadeIn: { from: { opacity: 0 }, to: { opacity: 1 } },
        ticker: { from: { transform: 'translateX(100%)' }, to: { transform: 'translateX(-100%)' } },
      },
    },
  },
  plugins: [],
}
