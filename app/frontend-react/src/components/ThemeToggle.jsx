import { useTheme } from '../context/ThemeContext'

const THEME_ICONS = {
  dark: '🌙',
  light: '☀️',
  midnight: '🌑',
  emerald: '💚',
  rose: '🌸',
}

const THEME_LABELS = {
  dark: 'Dark',
  light: 'Light',
  midnight: 'Midnight',
  emerald: 'Emerald',
  rose: 'Rose',
}

export default function ThemeToggle() {
  const { theme, cycleTheme, themes } = useTheme()
  const nextIdx = (themes.indexOf(theme) + 1) % themes.length
  const next = themes[nextIdx]

  return (
    <button
      onClick={cycleTheme}
      title={`Switch to ${THEME_LABELS[next]}`}
      className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-all duration-200 hover:opacity-80"
      style={{ background: 'var(--panel)', color: 'var(--text-dim)', border: '1px solid var(--border)' }}
    >
      <span className="text-base" role="img" aria-label={theme}>{THEME_ICONS[theme]}</span>
      <span className="hidden sm:inline">{THEME_LABELS[theme]}</span>
    </button>
  )
}
