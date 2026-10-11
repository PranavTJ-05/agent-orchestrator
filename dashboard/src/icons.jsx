const base = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }
const Svg = ({ children, ...p }) => <svg viewBox="0 0 24 24" {...base} {...p}>{children}</svg>

export const Sparkle = (p) => <Svg {...p}><path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" /><path d="M19 15l.7 1.8 1.8.7-1.8.7L19 20l-.7-1.8-1.8-.7 1.8-.7z" /></Svg>
export const Plug = (p) => <Svg {...p}><path d="M9 3v5M15 3v5M6 8h12v3a6 6 0 01-12 0z" /><path d="M12 17v4" /></Svg>
export const Pulse = (p) => <Svg {...p}><path d="M3 12h4l2.5-6 4 12 2.5-6H21" /></Svg>
export const Chart = (p) => <Svg {...p}><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" /></Svg>
export const People = (p) => <Svg {...p}><circle cx="9" cy="8" r="3.2" /><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6" /><path d="M16 5.5a3 3 0 010 5.6M18 14.3c1.8.8 3 2.6 3 4.7" /></Svg>
export const Plus = (p) => <Svg {...p}><path d="M12 5v14M5 12h14" /></Svg>
export const Chevron = (p) => <Svg {...p}><path d="M9 6l6 6-6 6" /></Svg>
export const Close = (p) => <Svg {...p}><path d="M6 6l12 12M18 6L6 18" /></Svg>
export const Refresh = (p) => <Svg {...p}><path d="M20 11a8 8 0 10-2.3 5.7" /><path d="M20 4v7h-7" /></Svg>
export const Trash = (p) => <Svg {...p}><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" /></Svg>
export const Edit = (p) => <Svg {...p}><path d="M4 20h4L19 9l-4-4L4 16z" /></Svg>
export const Shield = (p) => <Svg {...p}><path d="M12 3l8 3v6c0 4.5-3.2 7.8-8 9-4.8-1.2-8-4.5-8-9V6z" /></Svg>
export const Warning = (p) => <Svg {...p}><path d="M12 4l9 16H3z" /><path d="M12 10v4M12 17.2v.1" /></Svg>
export const Arrow = (p) => <Svg {...p}><path d="M5 12h14M13 6l6 6-6 6" /></Svg>
export const Search = (p) => <Svg {...p}><circle cx="11" cy="11" r="6.5" /><path d="M16 16l4 4" /></Svg>
export const Bolt = (p) => <Svg {...p}><path d="M13 3L5 14h6l-1 7 8-11h-6z" /></Svg>
