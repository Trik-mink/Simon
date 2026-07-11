import { useState } from 'react'

const MODE_COPY = {
  study: 'Study marker locked',
  electronics: 'Circuit marker locked',
  tabletop: 'Tabletop marker locked',
}

export default function CameraPreview({ live, mode, phase }) {
  const [streamKey, setStreamKey] = useState(0)

  // An MJPEG <img> never reconnects after the stream drops (backend restart,
  // network hiccup) — remount it with a cache-busted URL to retry.
  const handleError = () => {
    setTimeout(() => setStreamKey((k) => k + 1), 2000)
  }

  return (
    <section className="scanner-panel" aria-label="Desk camera scanner">
      <div className="scanner-header">
        <div>
          <span className="panel-kicker">Scanner viewport</span>
          <h2>Desk feed</h2>
        </div>
        <span className={`scanner-chip ${live ? 'online' : 'offline'}`}>
          {live ? 'Cam link' : 'No link'}
        </span>
      </div>

      <div className="viewport-shell">
        <img
          key={streamKey}
          src={`/camera/stream?r=${streamKey}`}
          alt="Live desk camera feed"
          onError={handleError}
        />
        <span className="corner top-left" />
        <span className="corner top-right" />
        <span className="corner bottom-left" />
        <span className="corner bottom-right" />
        <div className="scanline" aria-hidden="true" />
        <div className="viewport-readout">
          <span>{MODE_COPY[mode] || 'Free scan'}</span>
          <span>{phase === 'thinking' ? 'Analyzing' : 'Standing by'}</span>
        </div>
      </div>
    </section>
  )
}
