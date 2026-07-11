import { useEffect, useMemo, useRef, useState } from 'react'
import CameraPreview from './components/CameraPreview'
import VoiceInput from './components/VoiceInput'
import SimonChat from './components/SimonChat'

const EMOTION_LABELS = {
  dance: 'Ready',
  thinking: 'Thinking',
  study: 'Study quest',
  nonchalant: 'Idle',
  sad: 'Needs help',
}

const MODE_LABELS = {
  study: 'Study',
  electronics: 'Circuit',
  tabletop: 'Tabletop',
}

const ALIGNMENT_STORAGE_KEY = 'projected-copilot-alignment-checked'

function readAlignmentChecked() {
  try {
    return window.localStorage?.getItem(ALIGNMENT_STORAGE_KEY) === 'true'
  } catch {
    return false
  }
}

function chooseVoice() {
  const voices = window.speechSynthesis?.getVoices?.() || []
  return (
    voices.find((voice) => /samantha|karen|victoria|zira|junior/i.test(voice.name)) ||
    voices.find((voice) => voice.lang.startsWith('en'))
  )
}

function speak(text, onEnd) {
  if (!text || !window.speechSynthesis) return
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.pitch = 2.0
  utterance.rate = 1.15
  utterance.volume = 1.0
  const voice = chooseVoice()
  if (voice) utterance.voice = voice
  if (onEnd) utterance.onend = onEnd
  window.speechSynthesis.speak(utterance)
}

export default function App() {
  const [text, setText] = useState('')
  const [response, setResponse] = useState(null)
  const [emotion, setEmotion] = useState('dance')
  const [live, setLive] = useState(false)
  const [mode, setMode] = useState(null)
  const [phase, setPhase] = useState('watching')
  const [systemStatus, setSystemStatus] = useState(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [alignmentChecked, setAlignmentChecked] = useState(readAlignmentChecked)
  const [currentAnswer, setCurrentAnswer] = useState(null)
  const [scanHistory, setScanHistory] = useState([])
  const wsRef = useRef(null)
  const voiceRef = useRef(null)
  const pendingAnswerRef = useRef(null)

  const fetchStatus = async () => {
    try {
      const res = await fetch('/status')
      const data = await res.json()
      setSystemStatus(data)
      if (data.mode !== undefined) setMode(data.mode || null)
    } catch {
      setSystemStatus(null)
    }
  }

  useEffect(() => {
    fetchStatus()
    const timer = window.setInterval(fetchStatus, 3000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    if (systemStatus?.pointing && !systemStatus.pointing.calibrated) {
      setAlignmentChecked(false)
    }
  }, [systemStatus?.pointing?.calibrated])

  useEffect(() => {
    try {
      window.localStorage?.setItem(ALIGNMENT_STORAGE_KEY, alignmentChecked ? 'true' : 'false')
    } catch {
      // localStorage can be unavailable in private or restricted browser contexts.
    }
  }, [alignmentChecked])

  const rememberAnswer = (data, source = 'Scan') => {
    const answer = data.answer || data.guidance || ''
    if (!answer) return
    const item = {
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      source,
      answer,
      guidance: data.guidance || answer,
      emotion: data.emotion || 'dance',
      position: data.position || null,
      createdAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    }
    setCurrentAnswer(item)
    setResponse(answer)
    pendingAnswerRef.current = answer
    setScanHistory((history) => [item, ...history].slice(0, 3))
  }

  useEffect(() => {
    let reconnectTimer

    const connect = () => {
      const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${protocol}://${location.host}/ws/web`)
      wsRef.current = ws

      ws.onopen = () => {
        setLive(true)
        setPhase((current) => (current === 'offline' ? 'watching' : current))
        fetchStatus()
      }

      ws.onclose = () => {
        setLive(false)
        setPhase('offline')
        reconnectTimer = window.setTimeout(connect, 2000)
      }

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data)

        if (data.action === 'context') {
          setMode(data.mode || null)
          fetchStatus()
          return
        }

        if (data.action === 'scan_status') {
          setSystemStatus((current) => ({
            ...(current || {}),
            scan: data.scan,
          }))
          setPhase(data.scan?.in_flight ? 'thinking' : 'watching')
          return
        }

        if (data.action === 'projector_status') {
          setSystemStatus((current) => ({
            ...(current || {}),
            calibrated: data.pointing?.calibrated ?? current?.calibrated,
            pointing: data.pointing,
          }))
          return
        }

        if (data.action === 'error') {
          const message = data.message || 'Something went wrong.'
          setErrorMessage(message)
          setResponse(message)
          setEmotion('sad')
          setPhase('error')
          fetchStatus()
          return
        }

        if (data.action === 'stop') {
          window.speechSynthesis?.cancel()
          setPhase('paused')
          return
        }

        if (data.action === 'ask') {
          const message = data.guidance || 'How can I help you?'
          setResponse(message)
          setPhase('listening')
          speak(message, () => voiceRef.current?.startListening())
          return
        }

        if (data.action === 'reveal') {
          setPhase(pendingAnswerRef.current ? 'revealed' : 'watching')
          return
        }

        if (data.action === 'speak') {
          const answer = pendingAnswerRef.current
          if (answer) {
            window.speechSynthesis?.cancel()
            speak(answer)
            setPhase('speaking')
          }
          return
        }

        setEmotion(data.emotion || 'dance')
        if (data.guidance) {
          setErrorMessage('')
          rememberAnswer(data, 'Scan')
          setPhase('answer-ready')
          fetchStatus()
        }
      }
    }

    connect()
    return () => {
      window.clearTimeout(reconnectTimer)
      wsRef.current?.close()
    }
  }, [])

  const reveal = async () => {
    await fetch('/reveal', { method: 'POST' })
    setPhase(pendingAnswerRef.current ? 'revealed' : 'watching')
  }

  const scanAgain = async () => {
    setErrorMessage('')
    setPhase('thinking')
    try {
      const res = await fetch('/scan/request', { method: 'POST' })
      const data = await res.json()
      if (data.error) {
        const message = data.error || 'Scan is not available.'
        setErrorMessage(message)
        setPhase('error')
      }
    } catch {
      setErrorMessage('Simon could not request a scan.')
      setPhase('offline')
    }
    fetchStatus()
  }

  const speakCurrentAnswer = () => {
    const answer = currentAnswer?.answer || pendingAnswerRef.current
    if (!answer) return
    window.speechSynthesis?.cancel()
    speak(answer)
    setPhase('speaking')
  }

  const clearCurrentAnswer = () => {
    setCurrentAnswer(null)
    setResponse(null)
    pendingAnswerRef.current = null
    setPhase(live ? 'watching' : 'offline')
  }

  const resetSetup = async () => {
    setAlignmentChecked(false)
    setErrorMessage('')
    setResponse(null)
    setCurrentAnswer(null)
    setScanHistory([])
    pendingAnswerRef.current = null
    setPhase(live ? 'watching' : 'offline')
    try {
      await fetch('/reset', { method: 'POST' })
      fetchStatus()
    } catch {
      setErrorMessage('Simon could not reset the backend.')
    }
  }

  const ask = async (question) => {
    if (!question.trim()) return
    setResponse(null)
    setErrorMessage('')
    setEmotion('thinking')
    setPhase('thinking')
    try {
      const res = await fetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      })
      const data = await res.json()
      if (data.error) {
        const message = data.detail || data.error
        setResponse(message)
        setErrorMessage(message)
        setEmotion('sad')
        setPhase('error')
        fetchStatus()
        return
      }
      setEmotion(data.emotion || 'dance')
      rememberAnswer(data, 'Ask')
      setPhase('answer-ready')
      fetchStatus()
    } catch {
      setResponse('Simon could not reach the server.')
      setErrorMessage('Simon could not reach the server.')
      setEmotion('sad')
      setPhase('offline')
    }
    setText('')
  }

  const statusText = useMemo(() => {
    if (!live) return 'Reconnecting'
    if (phase === 'thinking') return 'Scanning'
    if (phase === 'answer-ready') return 'Answer ready'
    if (phase === 'listening') return 'Listening'
    if (phase === 'speaking') return 'Speaking'
    if (phase === 'paused') return 'Paused'
    if (phase === 'error') return 'Needs attention'
    return 'Watching'
  }, [live, phase])

  const readiness = useMemo(() => {
    const camera = systemStatus?.camera
    const claude = systemStatus?.claude
    const connections = systemStatus?.connections
    const scan = systemStatus?.scan
    const pointing = systemStatus?.pointing
    return [
      {
        label: 'Backend',
        value: live ? 'Connected' : 'Reconnecting',
        state: live ? 'ok' : 'bad',
      },
      {
        label: 'Camera',
        value: camera ? (camera.ready ? `Index ${camera.index}` : 'Unavailable') : 'Checking',
        state: camera ? (camera.ready ? 'ok' : 'bad') : 'warn',
      },
      {
        label: 'Claude',
        value: claude ? (claude.configured ? claude.model : 'Missing key') : 'Checking',
        state: claude ? (claude.configured ? 'ok' : 'bad') : 'warn',
      },
      {
        label: 'Projector',
        value: connections ? `${connections.projector} linked` : 'Checking',
        state: connections?.projector > 0 ? 'ok' : 'warn',
      },
      {
        label: 'Pointing',
        value: pointing
          ? pointing.test_point_enabled
            ? 'Test target'
            : pointing.ready
              ? 'Ready'
              : pointing.calibrated
                ? 'Off'
                : `Need ${pointing.table_markers_found || 0}/4`
          : 'Checking',
        state: pointing ? (pointing.ready || pointing.test_point_enabled ? 'ok' : 'warn') : 'warn',
      },
      {
        label: 'Scan',
        value: scan?.message || 'Ready',
        state: scan?.phase === 'failed' ? 'bad' : scan?.in_flight ? 'warn' : 'ok',
      },
    ]
  }, [live, systemStatus])

  const setupSteps = useMemo(() => {
    const camera = systemStatus?.camera
    const claude = systemStatus?.claude
    const connections = systemStatus?.connections
    const pointing = systemStatus?.pointing
    const scan = systemStatus?.scan
    const tableMarkersFound = pointing?.table_markers_found || 0
    const tableMarkersReady = Boolean(pointing?.calibrated || tableMarkersFound === 4)
    const scanReady = Boolean(scan && !scan.in_flight && scan.phase !== 'failed')

    return [
      {
        label: 'Backend connected',
        detail: live ? 'WebSocket link is live.' : 'Run ./start.sh and keep it open.',
        done: live,
      },
      {
        label: 'Camera ready',
        detail: camera?.ready ? `Using camera index ${camera.index}.` : 'Set CAMERA_INDEX in server/.env.',
        done: Boolean(camera?.ready),
      },
      {
        label: 'Claude configured',
        detail: claude?.configured ? claude.model : 'Add ANTHROPIC_API_KEY to server/.env.',
        done: Boolean(claude?.configured),
      },
      {
        label: 'Projector linked',
        detail: connections?.projector > 0 ? `${connections.projector} projector connection active.` : 'Start the projector window.',
        done: connections?.projector > 0,
      },
      {
        label: 'Table markers locked',
        detail: tableMarkersReady ? 'Markers 0-3 are calibrated.' : `${tableMarkersFound}/4 table markers detected.`,
        done: tableMarkersReady,
      },
      {
        label: 'Pointing enabled',
        detail: pointing?.ready ? 'Pointing is armed.' : 'Press p in the projector window.',
        done: Boolean(pointing?.ready),
      },
      {
        label: 'Test target checked',
        detail: alignmentChecked ? 'Alignment confirmed.' : 'Press t, verify the center target, then mark aligned.',
        done: alignmentChecked,
      },
      {
        label: 'Ready to scan',
        detail: scanReady ? 'Press 4 to scan the desk.' : scan?.message || 'Waiting for scan state.',
        done: scanReady && alignmentChecked && Boolean(pointing?.ready),
      },
    ]
  }, [alignmentChecked, live, systemStatus])

  const currentSetupIndex = setupSteps.findIndex((step) => !step.done)
  const setupComplete = currentSetupIndex === -1
  const pointWarning = systemStatus?.scan?.point_warning

  return (
    <main className="app-shell">
      <header className="topbar" aria-label="Simon status">
        <div className="brand-lockup">
          <div className="avatar-frame" aria-hidden="true">
            <img src="/simon-pixel.png" alt="" />
          </div>
          <div>
            <p className="eyebrow">Projected Copilot</p>
            <h1>Simon</h1>
          </div>
        </div>

        <div className="topbar-status">
          <span className={`signal-dot ${live ? 'is-live' : 'is-offline'}`} aria-hidden="true" />
          <span>{live ? 'Live link' : 'Offline'}</span>
        </div>
      </header>

      <section className="mission-strip" aria-label="Current mission state">
        <div className="mission-card primary">
          <span className="mission-label">Status</span>
          <strong>{statusText}</strong>
        </div>
        <div className="mission-card">
          <span className="mission-label">Mode</span>
          <strong>{mode ? MODE_LABELS[mode] || mode : 'Free play'}</strong>
        </div>
        <div className="mission-card">
          <span className="mission-label">Mood</span>
          <strong>{EMOTION_LABELS[emotion] || emotion}</strong>
        </div>
      </section>

      <section className="system-strip" aria-label="System readiness">
        {readiness.map((item) => (
          <div className={`system-item ${item.state}`} key={item.label}>
            <span className="system-label">{item.label}</span>
            <strong>{item.value}</strong>
          </div>
        ))}
      </section>

      <section className="setup-panel" aria-label="Guided setup">
        <div className="setup-header">
          <div>
            <span className="panel-kicker">Setup guide</span>
            <h2>{setupComplete ? 'Ready to scan' : setupSteps[currentSetupIndex].label}</h2>
          </div>
          <div className="setup-actions">
            <button
              className="setup-action"
              type="button"
              onClick={() => setAlignmentChecked((checked) => !checked)}
            >
              {alignmentChecked ? 'Clear aligned' : 'Mark aligned'}
            </button>
            <button className="setup-action secondary" type="button" onClick={resetSetup}>
              Reset setup
            </button>
          </div>
        </div>

        <ol className="setup-list">
          {setupSteps.map((step, index) => {
            const state = step.done ? 'done' : index === currentSetupIndex ? 'current' : 'waiting'
            return (
              <li className={`setup-step ${state}`} key={step.label}>
                <span className="step-index">{index + 1}</span>
                <div>
                  <strong>{step.label}</strong>
                  <p>{step.detail}</p>
                </div>
              </li>
            )
          })}
        </ol>
      </section>

      {errorMessage ? (
        <div className="system-alert" role="alert">
          {errorMessage}
        </div>
      ) : null}

      {pointWarning ? (
        <div className="system-alert warning" role="status">
          {pointWarning} Simon can still answer, but there is no visual point for this scan.
        </div>
      ) : null}

      <div className="hud-grid">
        <CameraPreview live={live} mode={mode} phase={phase} />

        <aside className="side-console" aria-label="Simon controls">
          <SimonChat message={response} emotion={emotion} phase={phase} />

          <div className="command-panel">
            <div className="panel-heading">
              <span>Command deck</span>
              <span className="panel-code">A-05</span>
            </div>

            <button className="primary-action" onClick={reveal} type="button">
              Reveal answer
            </button>

            <div className="control-grid" aria-label="Answer controls">
              <button className="secondary-action" onClick={scanAgain} type="button">
                Scan again
              </button>
              <button className="secondary-action" onClick={speakCurrentAnswer} type="button">
                Speak
              </button>
              <button className="secondary-action" onClick={clearCurrentAnswer} type="button">
                Clear
              </button>
            </div>

            <form
              className="ask-form"
              onSubmit={(event) => {
                event.preventDefault()
                ask(text)
              }}
            >
              <label htmlFor="ask-simon">Ask Simon</label>
              <div className="input-row">
                <input
                  id="ask-simon"
                  type="text"
                  placeholder="type a quest..."
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                />
                <button className="send-button" type="submit" aria-label="Send question">
                  Go
                </button>
              </div>
            </form>

            <VoiceInput ref={voiceRef} onTranscript={(transcript) => ask(transcript)} />
          </div>

          <section className="history-panel" aria-label="Recent scan history">
            <div className="panel-heading">
              <span>Recent answers</span>
              <span className="panel-code">{scanHistory.length}/3</span>
            </div>
            {scanHistory.length ? (
              <ol className="history-list">
                {scanHistory.map((item) => (
                  <li className="history-item" key={item.id}>
                    <div className="history-meta">
                      <span>{item.source}</span>
                      <span>{item.position ? 'Point' : 'No point'}</span>
                      <span>{item.createdAt}</span>
                    </div>
                    <p>{item.answer}</p>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="history-empty">No answers yet.</p>
            )}
          </section>
        </aside>
      </div>
    </main>
  )
}
