import { motion, useMotionValue, useTransform, type MotionValue } from 'framer-motion';
import { useRef, type ReactNode } from 'react';

interface BentoCardProps {
  icon: string;
  title: string;
  body: string;
  /** Grid span (3 default; 2/4 also available). */
  span?: 2 | 3 | 4;
  children?: ReactNode;
}

/**
 * BentoCard — карточка с mouse-tracking 3D tilt.
 * Использует useMotionValue + useTransform для максимально
 * дешёвой трансформации без re-render на каждое движение мыши.
 */
function BentoCard({ icon, title, body, span = 3, children }: BentoCardProps) {
  const ref = useRef<HTMLDivElement | null>(null);

  // MotionValues для rotation. Следим за ними через motion.div style.
  const mx: MotionValue<number> = useMotionValue(0.5);
  const my: MotionValue<number> = useMotionValue(0.5);
  const rotateX = useTransform(my, [0, 1], [6, -6]);
  const rotateY = useTransform(mx, [0, 1], [-6, 6]);

  return (
    <motion.div
      ref={ref}
      className={`bento-card span-${span}`}
      onMouseMove={(e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        mx.set((e.clientX - rect.left) / rect.width);
        my.set((e.clientY - rect.top)  / rect.height);
      }}
      onMouseLeave={() => {
        mx.set(0.5);
        my.set(0.5);
      }}
      style={{ rotateX, rotateY, transformPerspective: 1000, transformStyle: 'preserve-3d' }}
      transition={{ type: 'spring', stiffness: 220, damping: 22 }}
    >
      <div className="bento-icon">{icon}</div>
      <h3>{title}</h3>
      <p>{body}</p>
      {children}
    </motion.div>
  );
}

/**
 * BentoGrid — 6 ключевых модулей проекта.
 * Каждая карточка имеет mouse-tilt (3D rotation around center).
 */
export function Bento() {
  return (
    <section className="section" id="project" aria-labelledby="bento-title">
      <div className="section-header">
        <span className="section-eyebrow">Подробности по проекту</span>
        <h2 id="bento-title">ComfyUI как пайплайн из шести модулей</h2>
        <p className="section-subtitle">
          Не одна библиотека — а рабочий конвейер: окружение, ноды, симлинки на модели,
          распределение по двум GPU и публичный туннель. Каждый модуль идемпотентен.
        </p>
      </div>

      <div className="bento">
        <BentoCard
          icon="🚀"
          title="Запуск одной строкой"
          body="Три Python-скрипта в instal/: окружение, ноды, запуск. Через пару минут после старта получаете публичный URL на работающий ComfyUI."
        >
          <div className="stat">~2 мин до публичного URL</div>
        </BentoCard>

        <BentoCard
          icon="🛡️"
          title="Самовосстановление venv"
          body="Kaggle при рестарте сессии ломает venv (битый симлинк, слетевший +x). Скрипты ловят это и чинят автоматически за секунды — без переустановки torch."
        >
          <div className="stat">≈ 99% идемпотентность</div>
        </BentoCard>

        <BentoCard span={2} icon="⚡" title="torch cu130 под T4"
          body="Драйвер 580.x, нативный SDPA вместо нерабочего на Turing xformers." />
        <BentoCard span={2} icon="🧩" title="DisTorch2 на 2× GPU"
          body="ComfyUI-MultiGPU распределяет слои между двумя T4 и CPU аккуратно." />
        <BentoCard span={2} icon="📦" title="Модели через симлинки"
          body="Flux2 GGUF и LTX 2.3 из /kaggle/input. Один раз скопировал датасет — дальше мгновенно." />

        <BentoCard
          span={4}
          icon="🔗"
          title="Публичный URL прямо из ячейки"
          body="Cloudflare-туннель (trycloudflare.com) поднимается из блокнота без белого IP и без проброса портов. Под ячейкой появляются кнопки: открыть ComfyUI, остановить процесс, перезапустить с новым URL — ядро Kaggle при этом не перезапускается. Keep-alive не даёт Kaggle усыпить сессию через 40 минут бездействия."
        />

        <BentoCard span={2} icon="🌐" title="Публичные workflow"
          body="Flux2 GGUF, LTX 2.3 Director в workflows/ — готовые графы." />
      </div>
    </section>
  );
}
