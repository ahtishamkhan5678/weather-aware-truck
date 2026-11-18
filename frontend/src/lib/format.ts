const dateTime = new Intl.DateTimeFormat(undefined, {
  weekday: 'short',
  hour: '2-digit',
  minute: '2-digit',
})
const timeOnly = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' })
const dayMonth = new Intl.DateTimeFormat(undefined, { weekday: 'short', day: 'numeric', month: 'short' })

export const fmt = {
  miles: (mi: number) => `${Math.round(mi).toLocaleString()} mi`,
  milesPrecise: (mi: number) => `${mi.toFixed(mi < 10 ? 1 : 0)} mi`,
  duration(seconds: number): string {
    const m = Math.round(seconds / 60)
    const h = Math.floor(m / 60)
    if (h >= 24) return `${Math.floor(h / 24)}d ${h % 24}h ${String(m % 60).padStart(2, '0')}m`
    return h ? `${h}h ${String(m % 60).padStart(2, '0')}m` : `${m} min`
  },
  dateTime: (iso: string | Date) => dateTime.format(new Date(iso)),
  time: (iso: string | Date) => timeOnly.format(new Date(iso)),
  day: (iso: string | Date) => dayMonth.format(new Date(iso)),
  weight: (lb: number) => `${Math.round(lb).toLocaleString()} lb`,
  // One decimal: 24.7 mph must not display as "25" next to a Low (<25) classification.
  wind: (mph: number) => `${mph.toFixed(1)} mph`,
  rate: (inHr: number) => `${inHr.toFixed(2)} in/hr`,
}

/** Value for <input type="datetime-local"> in the user's local timezone. */
export function toLocalInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function nextHour(from = new Date()): Date {
  const d = new Date(from)
  d.setMinutes(0, 0, 0)
  d.setHours(d.getHours() + 1)
  return d
}
