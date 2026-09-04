import { useEffect, useRef } from 'react'
import gsap from 'gsap'

const TEXT = 'How can I help you today?'

function splitLetters(el) {
  el.innerHTML = ''
  let charIdx = 0
  const words = TEXT.split(' ')

  words.forEach((word, wi) => {
    const wordSpan = document.createElement('span')
    wordSpan.style.display = 'inline-block'
    wordSpan.style.whiteSpace = 'nowrap'

    word.split('').forEach(ch => {
      const s = document.createElement('span')
      s.className = 'letter'
      s.textContent = ch
      s.style.setProperty('--i', charIdx)
      wordSpan.appendChild(s)
      charIdx++
    })

    el.appendChild(wordSpan)
    if (wi < words.length - 1) {
      el.appendChild(document.createTextNode(' '))
    }
  })

  return el.querySelectorAll('.letter')
}

export default function Hero() {
  const wrapRef = useRef(null)
  const textRef = useRef(null)

  useEffect(() => {
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduced) return

    const letters = splitLetters(textRef.current)
    if (!letters.length) return

    const tl = gsap.timeline()

    // Entrance
    gsap.set(letters, { autoAlpha: 0, y: 28 })
    tl.to(letters, {
      autoAlpha: 1, y: 0,
      duration: 0.6, stagger: 0.025, ease: 'power3.out',
      delay: 0.2,
    })

    // Breathing
    gsap.to(letters, {
      yPercent: -5, scale: 1.03,
      duration: 1.8, ease: 'sine.inOut',
      repeat: -1, yoyo: true,
      stagger: { each: 0.05, from: 'start' },
    })

    // Beat loop
    const beats = [
      // wave
      (ls) => gsap.timeline()
        .to(ls, { y: -12, rotation: 4, duration: 0.28, ease: 'power2.out', stagger: 0.018 })
        .to(ls, { y: 0, rotation: 0, duration: 0.5, ease: 'elastic.out(1, 0.55)', stagger: 0.018 }, '-=0.08'),
      // bounce
      (ls) => gsap.timeline()
        .to(ls, { y: -18, duration: 0.24, ease: 'power2.out', stagger: 0.014 })
        .to(ls, { y: 0, duration: 0.55, ease: 'bounce.out', stagger: 0.014 }, '-=0.05'),
      // tilt
      (ls) => gsap.timeline()
        .to(ls, { rotation: (i) => (i % 2 ? 7 : -7), duration: 0.3, ease: 'power2.out', stagger: 0.016 })
        .to(ls, { rotation: 0, duration: 0.6, ease: 'elastic.out(1, 0.5)', stagger: 0.016 }, '-=0.1'),
    ]

    let beatId
    const startBeats = () => {
      beatId = setInterval(() => {
        const beat = beats[Math.floor(Math.random() * beats.length)]
        beat(letters)
      }, 4000)
    }
    setTimeout(startBeats, 1200)

    // Mouse parallax
    const px = gsap.quickTo(wrapRef.current, 'x', { duration: 0.7, ease: 'power3' })
    const py = gsap.quickTo(wrapRef.current, 'y', { duration: 0.7, ease: 'power3' })
    const onMove = (e) => {
      px((e.clientX / window.innerWidth - 0.5) * 16)
      py((e.clientY / window.innerHeight - 0.5) * 11)
    }
    document.addEventListener('mousemove', onMove)

    // Pause on tab hide
    const onVis = () => {
      if (document.hidden) { tl.pause(); gsap.globalTimeline.pause() }
      else { tl.resume(); gsap.globalTimeline.resume() }
    }
    document.addEventListener('visibilitychange', onVis)

    return () => {
      clearInterval(beatId)
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('visibilitychange', onVis)
    }
  }, [])

  return (
    <div ref={wrapRef} className="mb-4" style={{ willChange: 'transform' }}>
      <h1 ref={textRef} className="text-4xl md:text-5xl font-serif font-bold text-center" />
    </div>
  )
}
