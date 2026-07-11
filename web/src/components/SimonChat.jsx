const DEFAULT_LINES = {
  offline: 'I am trying to reconnect to the base station.',
  thinking: 'Scanning the desk. Hold steady.',
  watching: 'Place a marker, ask a question, or trigger a scan.',
  listening: 'I am listening.',
  paused: 'Speech paused.',
}

export default function SimonChat({ message, emotion, phase }) {
  const displayMessage = message || DEFAULT_LINES[phase] || DEFAULT_LINES.watching

  return (
    <section className="simon-panel" aria-label="Simon response">
      <div className="simon-card-top">
        <div className="simon-mini">
          <img src="/simon-pixel.png" alt="Simon pixel avatar" />
        </div>
        <div>
          <span className="panel-kicker">Simon says</span>
          <h2>{emotion?.toUpperCase() || 'READY'}</h2>
        </div>
      </div>

      <div className="dialogue-box">
        <p>{displayMessage}</p>
      </div>
    </section>
  )
}
