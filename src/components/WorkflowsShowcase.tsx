import { motion } from 'framer-motion';

/**
 * НОВАЯ ИНТЕРАКТИВНАЯ СЕКЦИЯ.
 *
 * WorkflowsShowcase — галерея готовых workflow с визуальными превью (SVG).
 * Каждая карточка hover-zoom (через Framer Motion scale + spring).
 * Реальные preview-картинки из workflows/ подгружались бы отдельно, пока —
 * стилизованные SVG превью (hot pink + neon).
 */
export function WorkflowsShowcase() {
  return (
    <section className="section" aria-labelledby="workflows-title">
      <div className="section-header">
        <span className="section-eyebrow">Workflows</span>
        <h2 id="workflows-title">Три готовых графа</h2>
        <p className="section-subtitle">
          Откройте в ComfyUI — они лежат как есть в репозитории. Никаких переменных окружения или скрытых зависимостей.
        </p>
      </div>

      <div className="workflows-grid">
        <WorkflowCard
          href="https://github.com/THE-ANGEL-AI/Kaggle_Workspace_FreeGPU/tree/main/workflows"
          title="Flux2 GGUF"
          tag="text-to-image"
          accent="cyan"
          previewKind="image"
        />
        <WorkflowCard
          href="https://github.com/THE-ANGEL-AI/Kaggle_Workspace_FreeGPU/tree/main/workflows"
          title="LTX 2.3 Six-Panel Director"
          tag="video"
          accent="magenta"
          previewKind="frames"
        />
        <WorkflowCard
          href="https://github.com/THE-ANGEL-AI/Kaggle_Workspace_FreeGPU/tree/main/workflows"
          title="TTS Pipeline"
          tag="speech"
          accent="violet"
          previewKind="wave"
        />
      </div>
    </section>
  );
}

interface WorkflowCardProps {
  href:  string;
  title: string;
  tag:   string;
  accent: 'cyan' | 'magenta' | 'violet';
  previewKind: 'image' | 'frames' | 'wave';
}

function WorkflowCard({ href, title, tag, accent, previewKind }: WorkflowCardProps) {
  return (
    <motion.a
      href={href}
      className={`workflow-card accent-${accent}`}
      target="_blank"
      rel="noopener noreferrer"
      initial={{ y: 0 }}
      whileHover={{ y: -6, transition: { type: 'spring', stiffness: 220, damping: 18 } }}
    >
      <div className="workflow-preview" aria-hidden="true">
        {previewKind === 'image'  && <ImagePreview />}
        {previewKind === 'frames' && <FramesPreview />}
        {previewKind === 'wave'   && <WavePreview />}
      </div>
      <div className="workflow-info">
        <h3>{title}</h3>
        <span className="workflow-tag">{tag}</span>
        <span className="arrow">→ открыть</span>
      </div>
    </motion.a>
  );
}

// === Svg previews ===
function ImagePreview() {
  return (
    <svg viewBox="0 0 360 220" preserveAspectRatio="xMidYMid slice">
      <defs>
        <radialGradient id="img-grad" cx="50%" cy="50%" r="60%">
          <stop offset="0%" stopColor="#00F0FF" stopOpacity="0.65" />
          <stop offset="100%" stopColor="#B026FF" stopOpacity="0.10" />
        </radialGradient>
        <pattern id="img-grid" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M 20 0 L 0 0 0 20" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="0.5" />
        </pattern>
      </defs>
      <rect width="360" height="220" fill="#0B0B16" />
      <rect width="360" height="220" fill="url(#img-grid)" />
      <circle cx="180" cy="110" r="80" fill="url(#img-grad)" />
      <circle cx="180" cy="110" r="80" fill="none" stroke="#00F0FF" strokeWidth="1" strokeDasharray="4 6" opacity="0.6">
        <animateTransform attributeName="transform" type="rotate" from="0 180 110" to="360 180 110" dur="14s" repeatCount="indefinite" />
      </circle>
      <text x="180" y="118" textAnchor="middle" fill="#00F0FF" fontSize="11" fontFamily="JetBrains Mono" letterSpacing="2">FLUX // DEV // GGUF</text>
    </svg>
  );
}
function FramesPreview() {
  return (
    <svg viewBox="0 0 360 220" preserveAspectRatio="xMidYMid slice">
      <rect width="360" height="220" fill="#0B0B16" />
      {[0, 1, 2, 3].map((i) => (
        <g key={i} transform={`translate(${20 + i * 80}, 40)`}>
          <rect width="68" height="48" fill="#1A1A2E" stroke="#FF003C" strokeWidth="0.8" opacity="0.8" />
          <circle cx="34" cy="24" r="6" fill="#FF003C">
            {i % 2 === 0 && <animate attributeName="opacity" values="1;0.3;1" dur={`${1 + i * 0.3}s`} repeatCount="indefinite" />}
          </circle>
          <text x="34" y="60" textAnchor="middle" fill="#FF003C" fontSize="7" fontFamily="JetBrains Mono">F{i + 1}</text>
        </g>
      ))}
      <text x="180" y="140" textAnchor="middle" fill="#FF003C" fontSize="11" fontFamily="JetBrains Mono" letterSpacing="2">LTX-VIDEO // 2.3</text>
    </svg>
  );
}
function WavePreview() {
  return (
    <svg viewBox="0 0 360 220" preserveAspectRatio="xMidYMid slice">
      <rect width="360" height="220" fill="#0B0B16" />
      <path d="M0,110 Q60,40 120,90 T240,80 T360,110" fill="none" stroke="#B026FF" strokeWidth="2" opacity="0.7">
        <animate attributeName="d"
          values="M0,110 Q60,40 120,90 T240,80 T360,110;
                  M0,110 Q60,80 120,40 T240,90 T360,110;
                  M0,110 Q60,40 120,90 T240,80 T360,110"
          dur="3s" repeatCount="indefinite" />
      </path>
      <path d="M0,140 Q60,170 120,150 T240,160 T360,140" fill="none" stroke="#B026FF" strokeWidth="1.5" opacity="0.4" />
      <text x="180" y="200" textAnchor="middle" fill="#B026FF" fontSize="10" fontFamily="JetBrains Mono" letterSpacing="2">TTS // WAVEFORM</text>
    </svg>
  );
}
