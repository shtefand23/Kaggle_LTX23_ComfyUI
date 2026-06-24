import { motion } from 'framer-motion';
import { useRef } from 'react';

interface Step {
  num:    string;
  title:  string;
  detail: string;
  badge:  string;
}

const steps: Step[] = [
  {
    num: '01',
    title: 'Окружение и зависимости',
    detail: 'uv поднимает Python 3.12 и venv, ставится torch cu130 + ComfyUI + Manager. Идемпотентно: если уже стоит — пропускается.',
    badge: '~40s',
  },
  {
    num: '02',
    title: 'Кастомные ноды и модели',
    detail: 'Симлинки на модели из /kaggle/input (Flux2 GGUF, LTX 2.3). ComfyUI-Manager ставит недостающие ноды из реестра.',
    badge: '~25s',
  },
  {
    num: '03',
    title: 'Запуск + публичный URL',
    detail: 'Поднимается ComfyUI на 2× T4, Cloudflare-туннель пробрасывает порт наружу. Появляются кнопки keep-alive.',
    badge: '~12s',
  },
];

function StepItem({ step }: { step: Step }) {
  return (
    <motion.article
      className="stepper-item"
      initial={{ '--p': 0 } as Record<string, number>}
      whileInView={{ '--p': 1 } as Record<string, number>}
      viewport={{ once: false, amount: 0.35 }}
      transition={{ duration: 0.6 }}
    >
      <div className="stepper-num">{step.num}</div>
      <div className="stepper-content">
        <h3>{step.title}</h3>
        <p>{step.detail}</p>
      </div>
      <div className="stepper-badge" aria-label={`Длительность шага ${step.badge}`}>{step.badge}</div>
    </motion.article>
  );
}

/**
 * InstallStepper — прогрессивное раскрытие шагов установки по мере скролла.
 *
 * Использует Framer Motion whileInView для каждого шага: CSS-переменная --p
 * (0..1) поднимается до 1 когда шаг входит в viewport, и стилизованные
 * свойства через calc(var(--p) ...) дают glow-эффект.
 *
 * Эффект scroll-driven без useTransform внутри map — declarative API
 * не нарушает rules of hooks.
 */
export function InstallStepper() {
  const ref = useRef<HTMLElement | null>(null);

  return (
    <section className="section" ref={ref} aria-labelledby="stepper-title">
      <div className="section-header">
        <span className="section-eyebrow">Timeline</span>
        <h2 id="stepper-title">Как это работает — по шагам</h2>
        <p className="section-subtitle">
          Прокручивайте вниз — каждый шаг подсветится, когда подойдёт его черёд.
          Суммарно ~80 секунд от клонирования до публичного ComfyUI.
        </p>
      </div>

      <div className="stepper-rail">
        {steps.map((step, i) => (
          <StepItem key={i} step={step} />
        ))}
      </div>
    </section>
  );
}
