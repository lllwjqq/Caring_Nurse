/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // 语义色全部走 CSS 变量（见 src/index.css），保证高对比/大字模式可覆盖
        primary: 'rgb(var(--c-primary) / <alpha-value>)',
        'primary-deep': 'rgb(var(--c-primary-deep) / <alpha-value>)',
        nurse: 'rgb(var(--c-nurse) / <alpha-value>)',
        ink: 'rgb(var(--c-ink) / <alpha-value>)',
        'ink-soft': 'rgb(var(--c-ink-soft) / <alpha-value>)',
        line: 'rgb(var(--c-line) / <alpha-value>)',
        mist: 'rgb(var(--c-mist) / <alpha-value>)',
        'level-green': 'rgb(var(--c-level-green) / <alpha-value>)',
        'level-yellow': 'rgb(var(--c-level-yellow) / <alpha-value>)',
        'level-yellow-ink': 'rgb(var(--c-level-yellow-ink) / <alpha-value>)',
        'level-orange': 'rgb(var(--c-level-orange) / <alpha-value>)',
        'level-red': 'rgb(var(--c-level-red) / <alpha-value>)',
        safe: 'rgb(var(--c-safe) / <alpha-value>)',
        warn: 'rgb(var(--c-warn) / <alpha-value>)',
        danger: 'rgb(var(--c-danger) / <alpha-value>)',
      },
      borderRadius: {
        card: '24px',
        btn: '16px',
      },
      boxShadow: {
        card: '0 2px 8px rgba(27,42,58,0.06)',
        'card-lg': '0 8px 24px rgba(27,42,58,0.10)',
      },
      maxWidth: {
        shell: '560px',
      },
    },
  },
  plugins: [],
}
