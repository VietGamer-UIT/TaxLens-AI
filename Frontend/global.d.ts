// =============================================================================
// TaxLens-AI :: Global Type Declarations
// Copyright: TaxLens-AI by Đoàn Hoàng Việt (Việt Gamer)
// =============================================================================
// This file shims the global `process` object for the TypeScript language
// server BEFORE `npm install` runs and @types/node becomes available.
//
// Why needed?
//   Next.js replaces process.env.NEXT_PUBLIC_* at BUILD TIME via webpack,
//   but TypeScript still needs the type to resolve `process` as a name.
//   Once `npm install` is done, @types/node provides this automatically and
//   this file becomes a harmless no-op (the declarations merge).
// =============================================================================

declare namespace NodeJS {
  interface ProcessEnv {
    readonly NODE_ENV: 'development' | 'production' | 'test'
    readonly NEXT_PUBLIC_API_URL?: string
    readonly [key: string]: string | undefined
  }
}

declare const process: {
  readonly env: NodeJS.ProcessEnv
}
