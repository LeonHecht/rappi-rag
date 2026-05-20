import { useState, useRef, useEffect } from 'react';

const PLACEHOLDER_QUESTIONS = [
  "Resume los documentos sobre politicas internas.",
  "Busca informacion sobre el criterio X.",
  "Compara estos documentos por fecha y tema.",
  "Extrae riesgos mencionados en este archivo.",
  "Busca documentos relacionados con este concepto.",
  "Resume los puntos principales con citas.",
  "Identifica contradicciones entre estos textos.",
  "Muestra fuentes que respalden esta afirmacion.",
  "Explica este documento para un usuario no tecnico.",
  "Genera una respuesta basada en la base de conocimiento."
];

export default function ChatBox({ onSend, placeholder }) {
  const [value, setValue] = useState('');
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isAnimating, setIsAnimating] = useState(false);
  const textareaRef = useRef(null);

  useEffect(() => {
    const interval = setInterval(() => {
      setIsAnimating(true);
      setTimeout(() => {
        setCurrentIndex((prev) => (prev + 1) % PLACEHOLDER_QUESTIONS.length);
        setIsAnimating(false);
      }, 300);
    }, 2000);

    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed) return;
    onSend?.(trimmed);
    setValue('');
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="w-full max-w-2xl mx-auto">
      <div className="flex items-center gap-3 bg-neutral-50 rounded-2xl px-3 py-2 hover:bg-neutral-100 focus:bg-neutral-100 transition-colors">
        <div className="flex-1 relative overflow-hidden flex items-center">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            className="w-full resize-none bg-transparent focus:outline-none text-sm text-neutral-800 leading-relaxed relative z-10 caret-neutral-800"
            style={{
              color: value ? 'inherit' : 'transparent',
            }}
            placeholder={placeholder}
          />
          {!value && (
            <div className="absolute inset-0 pointer-events-none overflow-hidden flex items-center">
              <div
                className={`text-sm text-neutral-400 leading-relaxed transition-transform duration-500 ${
                  isAnimating ? 'translate-y-full opacity-0' : 'translate-y-0 opacity-100'
                }`}
              >
                {placeholder || PLACEHOLDER_QUESTIONS[currentIndex]}
              </div>
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={handleSend}
          aria-label="Send message"
          className="shrink-0 h-8 w-8 rounded-full bg-neutral-900 hover:bg-black transition flex items-center justify-center disabled:opacity-40"
          disabled={!value.trim()}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="h-4 w-4 text-white"
          >
            <path d="M12 19V5" />
            <path d="M5 12l7-7 7 7" />
          </svg>
        </button>
      </div>
    </div>
  );
}
