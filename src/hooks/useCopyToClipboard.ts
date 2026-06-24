import { useCallback, useState } from 'react';

/**
 * Копирование текста в clipboard через navigator.clipboard API.
 * Возвращает [copied: boolean, copy: (text) => Promise<void>].
 * `copied` сбрасывается через 2 секунды (через timeout).
 */
export function useCopyToClipboard(timeoutMs = 2000): [boolean, (text: string) => Promise<void>] {
  const [copied, setCopied] = useState(false);

  const copy = useCallback(async (text: string) => {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else {
        // Fallback for non-secure context (HTTP localhost etc.)
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), timeoutMs);
    } catch (err) {
      console.warn('[copy] failed:', err);
      setCopied(false);
    }
  }, [timeoutMs]);

  return [copied, copy];
}
