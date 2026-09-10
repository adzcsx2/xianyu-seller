/** @type {import('tailwindcss').Config} */

// 这里刻意**覆盖** Tailwind 的默认取值，而不是去改组件里的类名：
// 全站有 395 处 rounded-md、130+ 处 bg-gray-*，逐处替换既容易漏又难回退。
// 把 md 圆角调大、把 gray 色阶换成冷静的蓝灰调，所有组件一次到位。
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: '#93C5FD',
          50: '#EFF6FF',
          100: '#DBEAFE',
          200: '#BFDBFE',
          300: '#A7D3FC',
          400: '#93C5FD',
          500: '#60A5FA',
          600: '#3B82F6',
          700: '#2563EB',
          800: '#1D4ED8',
          900: '#1E3A8A',
          ink: '#0F2B46',
        },
        // 中性色阶：只带极轻微的蓝灰调，避免和淡蓝强调元素冲突。
        gray: {
          50: 'rgb(var(--gray-50) / <alpha-value>)',
          100: 'rgb(var(--gray-100) / <alpha-value>)',
          200: 'rgb(var(--gray-200) / <alpha-value>)',
          300: 'rgb(var(--gray-300) / <alpha-value>)',
          400: 'rgb(var(--gray-400) / <alpha-value>)',
          500: 'rgb(var(--gray-500) / <alpha-value>)',
          600: 'rgb(var(--gray-600) / <alpha-value>)',
          700: 'rgb(var(--gray-700) / <alpha-value>)',
          800: 'rgb(var(--gray-800) / <alpha-value>)',
          900: 'rgb(var(--gray-900) / <alpha-value>)',
        },
      },
      borderRadius: {
        // 覆盖默认值：DEFAULT 4px→8px、md 6px→10px、lg 8px→16px、xl 12px→20px
        DEFAULT: '8px',
        sm: '6px',
        md: '10px',
        lg: '16px',
        xl: '20px',
        '2xl': '24px',
        '3xl': '32px',
      },
      boxShadow: {
        brand: '0 6px 18px rgba(96, 165, 250, 0.30)',
        'brand-lg': '0 10px 28px rgba(59, 130, 246, 0.35)',
        soft: '0 1px 2px rgba(37, 99, 235, 0.06)',
        card: '0 6px 20px rgba(37, 99, 235, 0.10)',
      },
      fontFamily: {
        sans: [
          '-apple-system',
          'BlinkMacSystemFont',
          '"PingFang SC"',
          '"Hiragino Sans GB"',
          '"Microsoft YaHei"',
          '"Helvetica Neue"',
          'Helvetica',
          'Arial',
          'sans-serif',
        ],
      },
    },
  },
  plugins: [],
}
