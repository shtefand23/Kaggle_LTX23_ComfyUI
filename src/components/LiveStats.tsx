import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';

/**
 * НОВАЯ ИНТЕРАКТИВНАЯ СЕКЦИЯ.
 *
 * LiveStats — набор счётчиков, которые «тикают» в реальном времени.
 * Цифры выдуманные (не из реальной метрики), но РЕГУЛЯРНО обновляются,
 * чтобы создать ощущение живого дашборда.
 *
 * Реальная интеграция с API Kaggle / ComfyUI заняла бы больше
 * времени (нужен server-side endpoint). Здесь — атмосферный
 * stand-in, который легко заменить на real-fetcher.
 */
export function LiveStats() {
  // Стартовые значения — выдуманные, но реалистичные для free tier Kaggle.
  const initial = {
    gpuHours:  42,
    idempotent: 99,
    stagesOkoted: 12,
    recovery: 12,
  };
  const [stats, setStats] = useState(initial);

  useEffect(() => {
    const t = setInterval(() => {
      setStats((prev) => ({
        gpuHours:      prev.gpuHours + (Math.random() > 0.6 ? 1 : 0),
        idempotent:    Math.min(99.9, prev.idempotent + (Math.random() > 0.95 ? 0.1 : 0)),
        stagesOkoted:  prev.stagesOkoted,
        recovery:      Math.max(11, Math.min(14, prev.recovery + (Math.random() > 0.7 ? 1 : -1))),
      }));
    }, 1800);
    return () => clearInterval(t);
  }, []);

  return (
    <section className="section" aria-labelledby="stats-title">
      <div className="section-header">
        <span className="section-eyebrow">Live</span>
        <h2 id="stats-title">Live дашборд</h2>
        <p className="section-subtitle">
          Заглушка для будущего real-fetcher'а (через /kaggle API).
          Сейчас — атмосферный тикер. Цифры обновляются каждые ~2 секунды.
        </p>
      </div>

      <div className="stats-grid">
        <StatTile
          icon="⏱"
          label="часов GPU в неделю (free tier)"
          value={stats.gpuHours.toString()}
          unit="h"
          tone="cyan"
        />
        <StatTile
          icon="🛡"
          label="идемпотентность скриптов"
          value={stats.idempotent.toFixed(1)}
          unit="%"
          tone="magenta"
        />
        <StatTile
          icon="⚙"
          label="этапов без переустановки"
          value={stats.stagesOkoted.toString()}
          unit=""
          tone="violet"
        />
        <StatTile
          icon="♻"
          label="секунд до авто-восстановления"
          value={stats.recovery.toString()}
          unit="s"
          tone="yellow"
        />
      </div>
    </section>
  );
}

interface StatTileProps {
  icon:   string;
  label:  string;
  value:  string;
  unit:   string;
  tone:   'cyan' | 'magenta' | 'violet' | 'yellow';
}

function StatTile({ icon, label, value, unit, tone }: StatTileProps) {
  return (
    <motion.div
      className={`stat-tile tone-${tone}`}
      initial={{ scale: 1 }}
      animate={{ scale: [1, 1.04, 1] }}
      transition={{ duration: 1.8, times: [0, 0.5, 1], repeat: Infinity, repeatDelay: 4 }}
    >
      <div className="stat-tile-icon" aria-hidden="true">{icon}</div>
      <div className="stat-tile-value">
        <span>{value}</span>
        <span className="unit">{unit}</span>
      </div>
      <div className="stat-tile-label">{label}</div>
    </motion.div>
  );
}
