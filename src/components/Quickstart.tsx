import { useCopyToClipboard } from '../hooks/useCopyToClipboard';
import type { ReactNode } from 'react';

interface Cell {
  comment: string;
  code:  ReactNode;
}

const cells: Cell[] = [
  {
    comment: '# 0.  Скрипты из репозитория (или обновить, если уже склонировано)',
    code: <>!git clone https://github.com/THE-ANGEL-AI/Kaggle_Workspace_FreeGPU.git || \<br />{'  '}git -C Kaggle_Workspace_FreeGPU pull</>,
  },
  {
    comment: '# 1.  Окружение: uv + venv (Python 3.12) + torch cu130 + ComfyUI + Manager',
    code: <>!python Kaggle_Workspace_FreeGPU/instal/instal_comfyui.py</>,
  },
  {
    comment: '# 2.  Кастомные ноды + симлинки на модели из /kaggle/input',
    code: <>!python Kaggle_Workspace_FreeGPU/instal/instal_castom_node.py</>,
  },
  {
    comment: '# 3.  Запуск + Cloudflare-туннель + keep-alive кнопки',
    code: <>%run Kaggle_Workspace_FreeGPU/instal/start.py</>,
  },
];

function TerminalCell({ cell }: { cell: Cell }) {
  const [copied, copy] = useCopyToClipboard();

  // Сырое текстовое представление ячейки для копирования.
  const raw = `${cell.comment}\n${stripTags(cell.code)}`;

  return (
    <div className="terminal-cell">
      <span className="prompt">{cell.comment}</span>
      <div className="terminal-code">{cell.code}</div>
      <button
        type="button"
        className={`terminal-copy ${copied ? 'copied' : ''}`}
        onClick={() => copy(raw)}
        aria-label="Скопировать ячейку в clipboard"
      >
        {copied ? '✓ Скопировано' : '⧉ Copy'}
      </button>
    </div>
  );
}

/** Убирает React-узлы (без children.props.children) до плоской строки для clipboard. */
function stripTags(node: ReactNode): string {
  if (node == null || typeof node === 'boolean') return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(stripTags).join('');
  // React element
  if (typeof node === 'object' && 'props' in node) {
    return stripTags((node as { props: { children: ReactNode } }).props.children);
  }
  return '';
}

/**
 * Quickstart — fake-terminal в стиле macOS (traffic lights).
 * Каждая «ячейка» копируется в clipboard одной кнопкой.
 */
export function Quickstart() {
  return (
    <section className="section" id="start" aria-labelledby="start-title">
      <div className="section-header">
        <span className="section-eyebrow">Быстрый старт</span>
        <h2 id="start-title">Три ячейки — и ComfyUI работает</h2>
        <p className="section-subtitle">
          Включите в Kaggle-блокноте GPU T4 ×2 и интернет. Потом жмите Copy и вставляйте ячейки по порядку.
        </p>
      </div>

      <div className="terminal">
        <div className="terminal-bar" aria-hidden="true">
          <span className="dot red" />
          <span className="dot yellow" />
          <span className="dot green" />
          <span className="title">kaggle-notebook.ipynb — ComfyUI setup</span>
        </div>
        <div className="terminal-body">
          {cells.map((c, i) => (
            <TerminalCell key={i} cell={c} />
          ))}
        </div>
      </div>

      <p className="section-subtitle" style={{ marginTop: '1.4rem' }}>
        Можно и одной строкой: <code>%run .../instal/start.py</code> сам проверит окружение
        и вызовет нужный установщик автоматически.
      </p>
    </section>
  );
}
