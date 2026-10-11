// All calls go through the Vite proxy: /api/* -> http://localhost:8003/*
export async function api(path, { method = 'GET', body, signal } = {}) {
  const res = await fetch(`/api${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  })
  if (!res.ok) {
    let message = res.statusText || `Request failed (${res.status})`
    try {
      const data = await res.json()
      const detail = data.detail ?? data
      message = typeof detail === 'string' ? detail : detail.map?.((d) => d.msg).join('; ') || JSON.stringify(detail)
    } catch { /* keep the status text */ }
    throw new Error(message)
  }
  return res.status === 204 ? null : res.json()
}
