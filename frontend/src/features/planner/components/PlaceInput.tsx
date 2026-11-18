import { useEffect, useId, useRef, useState } from 'react'
import { api } from '../../../api/client'
import type { PlaceDTO } from '../../../api/types'
import type { PlaceInputState } from '../../../store/plannerStore'

interface Props {
  label: string
  marker: 'origin' | 'destination'
  value: PlaceInputState
  onChange: (v: PlaceInputState) => void
  placeholder: string
}

/** Debounced, abortable, keyboard-accessible autocomplete (ARIA combobox pattern). */
export function PlaceInput({ label, marker, value, onChange, placeholder }: Props) {
  const id = useId()
  const [results, setResults] = useState<PlaceDTO[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const [loading, setLoading] = useState(false)
  const skipNext = useRef(false)

  useEffect(() => {
    if (skipNext.current) {
      skipNext.current = false
      return
    }
    const q = value.text.trim()
    if (value.place || q.length < 3) return
    const ctrl = new AbortController()
    const t = setTimeout(async () => {
      setLoading(true)
      try {
        const r = await api.geocode(q, ctrl.signal)
        setResults(r)
        setActive(r.length ? 0 : -1)
        setOpen(true)
      } catch {
        /* typing continues; errors surface on submit */
      } finally {
        setLoading(false)
      }
    }, 250)
    return () => {
      clearTimeout(t)
      ctrl.abort()
    }
  }, [value.text, value.place])

  const query = value.text.trim()
  const visible = !value.place && query.length >= 3 ? results : []

  const choose = (p: PlaceDTO) => {
    skipNext.current = true
    onChange({ text: p.label, place: p })
    setOpen(false)
  }

  return (
    <div className={`field place place--${marker}`}>
      <label htmlFor={id}>{label}</label>
      <div className="place__control">
        <span className="place__dot" aria-hidden />
        <input
          id={id}
          role="combobox"
          aria-expanded={open && visible.length > 0}
          aria-controls={`${id}-list`}
          aria-autocomplete="list"
          autoComplete="off"
          placeholder={placeholder}
          value={value.text}
          onChange={(e) => onChange({ text: e.target.value, place: null })}
          onFocus={() => visible.length > 0 && setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          onKeyDown={(e) => {
            if (!open || !visible.length) return
            if (e.key === 'ArrowDown') {
              e.preventDefault()
              setActive((a) => (a + 1) % results.length)
            } else if (e.key === 'ArrowUp') {
              e.preventDefault()
              setActive((a) => (a - 1 + results.length) % results.length)
            } else if (e.key === 'Enter' && active >= 0) {
              e.preventDefault()
              choose(results[active])
            } else if (e.key === 'Escape') setOpen(false)
          }}
        />
        {loading && <span className="spinner spinner--sm" aria-label="Searching" />}
      </div>
      {open && visible.length > 0 && (
        <ul id={`${id}-list`} role="listbox" className="place__list">
          {visible.map((p, i) => (
            <li
              key={`${p.label}-${i}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? 'is-active' : ''}
              onMouseDown={(e) => {
                e.preventDefault()
                choose(p)
              }}
              onMouseEnter={() => setActive(i)}
            >
              {p.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
