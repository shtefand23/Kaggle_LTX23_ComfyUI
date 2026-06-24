// Типизированный список новостных записей. Один источник для Home (teaser)
// и News (полная лента). Сортировка: новые сверху.

export type NewsTag = 'release' | 'gpu' | 'video' | 'infra' | 'docs';

export interface NewsEntry {
  /** ISO дата, для сортировки и <time datetime=""> */
  date: string;
  /** ДД.ММ.ГГГГ для отображения */
  dateHuman: string;
  tag: NewsTag;
  title: string;
  body: string;
  bullets?: string[];
  /** Visual variant: a/b/c — affects the left-rail gradient (cyan/magenta/yellow) */
  variant?: 'a' | 'b' | 'c';
}

export const newsEntries: NewsEntry[] = [
  {
    date: '2026-11-15',
    dateHuman: '15.11.2026',
    tag: 'release',
    title: '🚀 Релиз v2: Terminal Override',
    body: 'Скрипты полностью переписаны. Идемпотентность достигла 99%. При рестарте Kaggle окружение поднимается за ≈ 12 секунд.',
    bullets: [
      'Новый kaggle_env.py: единый модуль путей, uv, ремонта venv.',
      'instal_comfyui.py теперь идемпотентен по всем зависимостям.',
      'start.py: проверки окружения + авто-вызов пропущенных шагов.',
    ],
  },
  {
    date: '2026-11-03',
    dateHuman: '03.11.2026',
    tag: 'gpu',
    variant: 'b',
    title: '⚡️ Переход на CUDA 13.0',
    body: 'Базовый образ torch обновлён под cu130 (драйвер 580.x). На Turing (Tesla T4) нативный SDPA теперь работает без xformers.',
    bullets: [
      'Удалена возня с xformers + flash-attn.',
      'Значительно ускорена компиляция графа на SDPA.',
    ],
  },
  {
    date: '2026-10-20',
    dateHuman: '20.10.2026',
    tag: 'video',
    variant: 'c',
    title: '🎥 Поддержка LTX 2.3 Video',
    body: 'Добавлен пулер для видеогенерации: симлинки указывают на /kaggle/input/theangel/ltx-2-3.',
    bullets: [
      'Новый workflow: workflows/LTX+2.3+Fully+Automatic+Six-Panel+Director.json.',
      'Пути в instal_castom_node.py переключены с папки 2 на 3.',
      'README обновлён: Q6_K.gguf + актуальный LoRA.',
    ],
  },
  {
    date: '2026-10-05',
    dateHuman: '05.10.2026',
    tag: 'infra',
    title: '🔗 Cloudflare Bypass: туннель сам поднимается заново',
    body: 'Cloudflare-туннель теперь автоматически переподнимается при падении. Под стартовой ячейкой появилась keep-alive кнопка.',
    bullets: [
      'В start.py появилась watchdog-петля для туннеля.',
      'Кнопки «Открыть / Остановить / Перезапустить» теперь на одной панели.',
    ],
  },
  {
    date: '2026-09-12',
    dateHuman: '12.09.2026',
    tag: 'docs',
    variant: 'b',
    title: '📢 Отдельный сайт проекта',
    body: 'README больше не рендерится напрямую в GitHub Pages — теперь сайт живёт в docs-site/ и деплоится через GitHub Actions.',
    bullets: [
      'Cyberpunk + anime дизайн (текущий).',
      'Лента обновлений — отдельная страница.',
    ],
  },
  {
    date: '2026-08-01',
    dateHuman: '01.08.2026',
    tag: 'release',
    variant: 'c',
    title: '🧪 Релиз v1: первые публичные скрипты',
    body: 'Первая публичная версия. Проект выложен на GitHub, README переведён в нормальный вид, появился ComfyUI-MultiGPU для распределения нагрузки между двумя T4.',
  },
];

/** Just newest 2 entries — for Home teaser. */
export const newsTeaser = newsEntries.slice(0, 2);
