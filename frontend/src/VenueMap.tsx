import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { areaLabel, useStrings, venueLabel } from './i18n'
import type { Venue } from './types'

/** Highest usage across a venue's areas, as a percentage, or null if unknown. */
function busiest(v: Venue): number | null {
  const pcts = Object.values(v.areas)
    .filter((a) => a.capacity > 0)
    .map((a) => (a.current / a.capacity) * 100)
  return pcts.length ? Math.max(...pcts) : null
}

/** Green below a third full, amber to two thirds, red above. */
function colorFor(pct: number | null): string {
  if (pct === null) return '#64748b'
  return pct < 34 ? '#16a34a' : pct < 67 ? '#d97706' : '#dc2626'
}

/** Great-circle distance in km. Twelve fixed points, so this runs on the
 *  viewer's device and their position is never sent anywhere. */
function distanceKm(aLat: number, aLon: number, bLat: number, bLon: number) {
  const R = 6371
  const dLat = ((bLat - aLat) * Math.PI) / 180
  const dLon = ((bLon - aLon) * Math.PI) / 180
  const la = (aLat * Math.PI) / 180
  const lb = (bLat * Math.PI) / 180
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(la) * Math.cos(lb) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

type Props = {
  venues: Venue[]
  selected: string
  onSelect: (id: string) => void
}

export default function VenueMap({ venues, selected, onSelect }: Props) {
  const host = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const layer = useRef<L.LayerGroup | null>(null)
  const [me, setMe] = useState<{ lat: number; lon: number } | null>(null)
  const [geoError, setGeoError] = useState<string | null>(null)
  const s = useStrings()

  useEffect(() => {
    if (!host.current || map.current) return
    map.current = L.map(host.current, {
      // A full-width map that eats the wheel traps the page: you scroll down
      // to it and cannot scroll past, because the wheel zooms instead. The
      // +/- buttons and pinch-to-zoom still work.
      scrollWheelZoom: false,
    }).setView([25.05, 121.55], 11)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap',
      maxZoom: 18,
    }).addTo(map.current)
    layer.current = L.layerGroup().addTo(map.current)
  }, [])

  // Markers are redrawn whenever the numbers change, so the colours track
  // occupancy rather than being fixed at first paint.
  useEffect(() => {
    if (!map.current || !layer.current) return
    layer.current.clearLayers()

    const placed = venues.filter((v) => v.lat !== null && v.lon !== null)
    for (const v of placed) {
      const pct = busiest(v)
      const isSelected = v.id === selected
      const marker = L.circleMarker([v.lat!, v.lon!], {
        radius: isSelected ? 11 : 8,
        color: isSelected ? '#e2e8f0' : colorFor(pct),
        weight: isSelected ? 3 : 1,
        fillColor: colorFor(pct),
        fillOpacity: 0.85,
      })

      const lines = Object.entries(v.areas).map(
        ([area, a]) => `${areaLabel(s, area)} ${a.current}/${a.capacity}`,
      )
      if (me) {
        lines.push(s.distanceAbout(distanceKm(me.lat, me.lon, v.lat!, v.lon!).toFixed(1)))
      }
      marker.bindTooltip(
        `<b>${venueLabel(s, v.id, v.name)}</b><br>${lines.join('<br>') || s.noDataNow}`,
      )
      marker.on('click', () => onSelect(v.id))
      marker.addTo(layer.current!)
    }

    if (me) {
      L.circleMarker([me.lat, me.lon], {
        radius: 6,
        color: '#2563eb',
        weight: 2,
        fillColor: '#2563eb',
        fillOpacity: 0.5,
      })
        .bindTooltip(s.yourLocation)
        .addTo(layer.current)
    }
  }, [venues, selected, me, onSelect, s])

  const locate = () => {
    setGeoError(null)
    if (!navigator.geolocation) {
      setGeoError(s.geoUnsupported)
      return
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setMe({ lat: pos.coords.latitude, lon: pos.coords.longitude })
        map.current?.setView([pos.coords.latitude, pos.coords.longitude], 13)
      },
      // Browsers only expose geolocation over HTTPS (localhost excepted), so
      // this fires on a plain-HTTP deployment as well as on a refusal.
      (err) => setGeoError(
        err.code === err.PERMISSION_DENIED
          ? s.geoDenied
          : s.geoFailed(err.message),
      ),
      { timeout: 10_000 },
    )
  }

  const nearest = me
    ? [...venues]
        .filter((v) => v.lat !== null && Object.keys(v.areas).length > 0)
        .map((v) => ({ v, km: distanceKm(me.lat, me.lon, v.lat!, v.lon!) }))
        .sort((a, b) => a.km - b.km)
        .slice(0, 3)
    : []

  return (
    <>
      <h2>
        {s.mapHeading}
        <span className="hours"> {s.mapLegend}</span>
      </h2>

      <div className="map-controls">
        <button onClick={locate}>{me ? s.relocate : s.useMyLocation}</button>
        {geoError && <span className="map-note error">{geoError}</span>}
        {me && <span className="map-note">{s.locationStaysHere}</span>}
      </div>

      <div ref={host} className="map" />

      {nearest.length > 0 && (
        <p className="map-note">
          {s.nearestToYou}
          {nearest.map(({ v, km }, i) => (
            <span key={v.id}>
              {i > 0 && '、'}
              <button className="linklike" onClick={() => onSelect(v.id)}>
                {venueLabel(s, v.id, v.name)}
              </button>{' '}
              {km.toFixed(1)} km
            </span>
          ))}
        </p>
      )}
    </>
  )
}
