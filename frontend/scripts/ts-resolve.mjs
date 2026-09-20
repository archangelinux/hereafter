// Lets plain Node run the app's extensionless TypeScript imports (Vite and tsc allow them), for scripts/*.test.mts only.
export async function resolve(specifier, context, next) {
  if (/^\.{1,2}\//.test(specifier) && !/\.[cm]?[jt]sx?$/.test(specifier)) {
    try {
      return await next(`${specifier}.ts`, context)
    } catch {
      /* not a .ts file: fall through */
    }
  }
  return next(specifier, context)
}
