import { createContext, useContext, useState, useEffect, useCallback } from 'react'

const THEMES = ['dark', 'light', 'midnight', 'emerald', 'rose']

const ThemeContext = createContext(null)

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'dark')

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  const cycleTheme = useCallback(() => {
    setTheme(prev => {
      const idx = THEMES.indexOf(prev)
      return THEMES[(idx + 1) % THEMES.length]
    })
  }, [])

  return (
    <ThemeContext.Provider value={{ theme, setTheme, cycleTheme, themes: THEMES }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider')
  return ctx
}
