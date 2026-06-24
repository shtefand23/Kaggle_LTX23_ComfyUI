import { motion, useScroll, useTransform, useMotionValue } from 'framer-motion';
import { useEffect, useRef, type CSSProperties } from 'react';
import { useMousePosition } from '../hooks/useMousePosition';
import { useReducedMotion } from '../hooks/useReducedMotion';

const ASSET_BASE = import.meta.env.BASE_URL;

/**
 * Hero — главный экран лендинга.
 *
 * Интерактивные эффекты:
 *   1. Mouse-tracking spotlight за персонажем: CSS-переменные --mx / --my
 *      обновляются через useMotionValue (без re-render).
 *      Framer Motion позволяет нативно передавать motionValue<int> в inline style
 *      под CSS-custom-property — это работает и не требует подписки.
 *   2. Scroll-driven parallax: background / text / character едут с разной
 *      скоростью (useScroll + useTransform), даёт глубину.
 *   3. Усиленный glitch на title: variants с дискретными keyframes — теперь
 *      дергается не только постоянно, но и по hover персонажа (через group).
 *   4. Floating + glow-drift (CSS) — сохранены из vanilla baseline.
 *
 * Отключаются при prefers-reduced-motion (useReducedMotion).
 */
export function Hero() {
  const reduced = useReducedMotion();
  const mouse = useMousePosition();

  // MotionValues для mouse-tracking — не вызывают re-render при изменении.
  const mxMV = useMotionValue(50);
  const myMV = useMotionValue(50);

  useEffect(() => {
    if (reduced) return;
    mxMV.set(mouse.x);
    myMV.set(mouse.y);
  }, [mouse, mxMV, myMV, reduced]);

  // Scroll-driven parallax.
  const heroRef = useRef<HTMLElement | null>(null);
  const { scrollYProgress } = useScroll({
    target: heroRef,
    offset: ['start start', 'end start'],
  });
  const bgY     = useTransform(scrollYProgress, [0, 1], [0,    -60]);   // самый медленный
  const charY   = useTransform(scrollYProgress, [0, 1], [0,    -120]);  // средний
  const textY   = useTransform(scrollYProgress, [0, 1], [0,    -180]);  // быстрый
  const textOp  = useTransform(scrollYProgress, [0, 0.7], [1, 0.4]);

  // Glitch keyframes для заголовка.
  const glitchAnim = reduced
    ? {}
    : {
        x: [0, -2, 2, -1, 3, -2, 0],
        y: [0,  1, -1, 0, -1, 1, 0],
        transition: {
          duration: 3.6,
          times: [0, 0.93, 0.94, 0.95, 0.96, 0.97, 1],
          repeat: Infinity,
        },
      };

  // Inline style с motionValue для CSS-переменных spotlight.
  // Framer Motion поддерживает нативно: motionValue<int> -> CSS-custom-property.
  const mouseStyle: CSSProperties | undefined = reduced
    ? undefined
    : { '--mx': mxMV, '--my': myMV } as CSSProperties;

  return (
    <header className="hero" role="banner" ref={heroRef}>
      <motion.div
        className="hero-bg-layer"
        aria-hidden="true"
        style={reduced ? undefined : { y: bgY }}
      />

      <div className="hero-grid">
        <motion.div
          className="hero-inner"
          style={reduced ? undefined : { y: textY, opacity: textOp }}
        >
          <motion.h1
            className="hero-title"
            data-text="ComfyUI на 2× Tesla T4"
            initial={{ x: 0, y: 0, opacity: 1 }}
            animate={glitchAnim}
          >
            ComfyUI на<br />
            <span className="neon">2× Tesla T4</span>
          </motion.h1>

          <p className="hero-sub">
            Flux2 GGUF · LTX 2.3 Video · TTS — без своего GPU, без оплаты облака.
            <br />
            Идемпотентные скрипты и публичный туннель прямо из Kaggle-блокнота.
          </p>

          <div className="hero-tags" aria-label="Технологический стек">
            <span className="hero-tag">Python 3.12</span>
            <span className="hero-tag">torch cu130</span>
            <span className="hero-tag">uv</span>
            <span className="hero-tag">ComfyUI 0.24+</span>
            <span className="hero-tag hot">2× Tesla T4</span>
          </div>

          <div className="hero-cta">
            <a className="btn btn-primary" href="https://github.com/THE-ANGEL-AI/Kaggle_Workspace_FreeGPU">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M12 .3a12 12 0 0 0-3.8 23.4c.6.1.8-.3.8-.6v-2.3c-3.3.7-4-1.6-4-1.6-.6-1.4-1.4-1.8-1.4-1.8-1.1-.7.1-.7.1-.7 1.2.1 1.9 1.2 1.9 1.2 1.1 1.9 2.9 1.4 3.6 1 .1-.8.4-1.4.8-1.7-2.7-.3-5.5-1.3-5.5-6 0-1.3.5-2.4 1.2-3.2-.1-.3-.5-1.5.1-3.2 0 0 1-.3 3.3 1.2a11.5 11.5 0 0 1 6 0c2.3-1.5 3.3-1.2 3.3-1.2.6 1.7.2 2.9.1 3.2.8.8 1.2 1.9 1.2 3.2 0 4.7-2.8 5.7-5.5 6 .4.4.8 1.1.8 2.2v3.3c0 .3.2.7.8.6A12 12 0 0 0 12 .3" />
              </svg>
              GitHub
            </a>
            <a className="btn btn-secondary" href="https://boosty.to/the_angel/donate">
              💖 Поддержать
            </a>
          </div>
        </motion.div>

        <motion.figure
          className="hero-figure"
          aria-label="Талисман проекта — THE ANGEL AI"
          style={reduced ? undefined : { y: charY }}
        >
          {/* Mouse-tracking spotlight (за персонажем, следует за курсором) */}
          <motion.div
            className="hero-mouse-glow"
            aria-hidden="true"
            style={mouseStyle}
          />

          {/* Статичный glow halo (cyan/magenta/violet blend) */}
          <div className="hero-character-glow" aria-hidden="true" />

          <div className="hero-character-frame">
            <img
              className="hero-character"
              src={`${ASSET_BASE}assets/character.png`}
              width="640"
              height="360"
              alt="Киберпанк-талисман THE ANGEL AI — главный персонаж проекта"
              decoding="async"
              loading="eager"
              fetchPriority="high"
            />
            <span className="hero-character-corner tl" aria-hidden="true" />
            <span className="hero-character-corner tr" aria-hidden="true" />
            <span className="hero-character-corner bl" aria-hidden="true" />
            <span className="hero-character-corner br" aria-hidden="true" />
          </div>

          <figcaption className="hero-character-caption">// mascot.v2.6 — flux_dev</figcaption>
        </motion.figure>
      </div>

      <div className="hero-glow-line" aria-hidden="true" />
    </header>
  );
}
