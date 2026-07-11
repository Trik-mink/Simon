import { forwardRef, useImperativeHandle, useRef, useState } from 'react'

const VoiceInput = forwardRef(function VoiceInput({ onTranscript }, ref) {
  const [listening, setListening] = useState(false)
  const recognitionRef = useRef(null)

  const startListening = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR || listening) return
    const rec = new SR()
    rec.lang = 'en-US'
    rec.interimResults = false
    rec.onresult = (e) => onTranscript(e.results[0][0].transcript)
    rec.onend = () => setListening(false)
    rec.start()
    recognitionRef.current = rec
    setListening(true)
  }

  const stopListening = () => {
    recognitionRef.current?.stop()
    setListening(false)
  }

  useImperativeHandle(ref, () => ({ startListening }))

  return (
    <button
      className={`voice-button ${listening ? 'is-listening' : ''}`}
      onMouseDown={startListening}
      onMouseUp={stopListening}
      onTouchStart={startListening}
      onTouchEnd={stopListening}
      type="button"
      aria-pressed={listening}
    >
      <span aria-hidden="true">{listening ? 'REC' : 'MIC'}</span>
      {listening ? 'Listening...' : 'Hold to speak'}
    </button>
  )
})

export default VoiceInput
