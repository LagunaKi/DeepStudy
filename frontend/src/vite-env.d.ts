/// <reference types="vite/client" />

export interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  // 其他环境变量...
}

export interface ImportMeta {
  readonly env: ImportMetaEnv;
}
