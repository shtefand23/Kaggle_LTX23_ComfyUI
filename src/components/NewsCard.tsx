import type { NewsEntry } from '../data/news';

interface NewsCardProps {
  entry: NewsEntry;
}

/**
 * Универсальная карточка новости. variant ∈ {a/b/c} влияет на цвет rail:
 * 'a' — по умолчанию cyan/magenta gradient
 * 'b' — magenta/violet
 * 'c' — yellow/cyan
 */
export function NewsCard({ entry }: NewsCardProps) {
  const variantClass = entry.variant ? ` pl-${variantToToken(entry.variant)}` : '';
  const tagText = entry.tag.toUpperCase();

  return (
    <article className={`news-entry${variantClass}`}>
      <div className="news-meta">
        <time dateTime={entry.date}>{entry.dateHuman}</time>
        <span className="tag">{tagText}</span>
      </div>
      <h3>{entry.title}</h3>
      <p>{entry.body}</p>
      {entry.bullets && entry.bullets.length > 0 && (
        <ul>
          {entry.bullets.map((b, i) => <li key={i}>{b}</li>)}
        </ul>
      )}
    </article>
  );
}

/** Маппинг a/b/c → CSS-token. 'a' остаётся дефолтным (нет доп. класса). */
function variantToToken(v: 'a' | 'b' | 'c'): 'magenta' | 'yellow' | 'a' {
  return v === 'b' ? 'magenta' : v === 'c' ? 'yellow' : 'a';
}
