const BASE = ''

export async function api(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  })

  if (res.status === 401) {
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}: ${text}`)
  }

  return res
}

export async function apiGet(path) {
  const res = await api(path)
  return res.json()
}

export async function apiPost(path, body) {
  const res = await api(path, {
    method: 'POST',
    body: JSON.stringify(body),
  })
  return res.json()
}

export async function apiDelete(path) {
  const res = await api(path, { method: 'DELETE' })
  return res.json()
}

export async function apiPatch(path, body) {
  const res = await api(path, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
  return res.json()
}

export async function apiStream(path, body, onChunk) {
  const res = await api(path, {
    method: 'POST',
    body: JSON.stringify(body),
  })

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    onChunk(buffer)
  }

  return buffer
}
