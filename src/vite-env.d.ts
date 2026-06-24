/// <reference types="vite/client" />

// Расширяем ImportMeta, чтобы TypeScript знал про import.meta.env.BASE_URL
// (поставляется vite/client automatically, но был конфликт — добавлена явная
// declaration для гарантии).
interface ImportMetaEnv {
  readonly BASE_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

// Дополнительные типы для asset imports через ?url / ?raw / ?worker. (опционально)
// Vite покрывает это сам, но декларация помогает в tsc --noEmit.
declare module '*?url' {
  const src: string;
  export default src;
}
declare module '*?raw' {
  const src: string;
  export default src;
}
