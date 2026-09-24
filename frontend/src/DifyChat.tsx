import { useEffect } from 'react'

/**
 * Mounts Dify's floating chat bubble.
 *
 * The token comes from a *published* Dify app's embed snippet, so there is
 * nothing to render until one exists. With no token this component renders
 * nothing at all rather than a button that fails when pressed.
 *
 * Both values are baked in at build time by Vite, which is why the Dockerfile
 * takes them as build args -- changing the token means rebuilding the image.
 */
const TOKEN = import.meta.env.VITE_DIFY_TOKEN as string | undefined
const BASE = (import.meta.env.VITE_DIFY_URL as string | undefined) ?? 'http://localhost'

export default function DifyChat() {
  useEffect(() => {
    if (!TOKEN) return
    // Guard against React 18/19 double-invoking effects in development, which
    // would otherwise inject the script twice and give you two bubbles.
    if (document.getElementById(TOKEN)) return

    ;(window as unknown as Record<string, unknown>).difyChatbotConfig = {
      token: TOKEN,
      baseUrl: BASE,
    }

    const script = document.createElement('script')
    script.src = `${BASE}/embed.min.js`
    script.id = TOKEN
    script.defer = true
    // Dify being down must not break the dashboard; the bubble just will not
    // appear, and the rest of the page is unaffected.
    script.onerror = () => console.warn(`Dify chat unavailable at ${BASE}`)
    document.body.appendChild(script)
  }, [])

  return null
}
