import { useEffect, useRef } from 'react'

function Particles() {
  const ref = useRef(null)

  useEffect(() => {
    const container = ref.current
    if (!container) return

    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (prefersReduced) return

    const count = 14
    for (let i = 0; i < count; i++) {
      const el = document.createElement('div')
      el.className = 'particle'
      const size = 2 + Math.random() * 3
      el.style.width = `${size}px`
      el.style.height = `${size}px`
      el.style.left = `${Math.random() * 100}vw`
      el.style.top = `${Math.random() * 100}vh`
      el.style.setProperty('--dur', `${12 + Math.random() * 14}s`)
      el.style.setProperty('--delay', `${Math.random() * 8}s`)
      el.style.setProperty('--dx', `${(Math.random() - 0.5) * 70}px`)
      el.style.setProperty('--dy', `${-25 - Math.random() * 55}px`)
      container.appendChild(el)
    }

    return () => { container.innerHTML = '' }
  }, [])

  return <div ref={ref} className="particles" />
}

export default function Background() {
  return (
    <>
      <div className="mesh-bg">
        <div className="mesh-blob blob-1" />
        <div className="mesh-blob blob-2" />
        <div className="mesh-blob blob-3" />
      </div>
      <Particles />
      <div className="vignette" />
    </>
  )
}
