import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // The public demo renders these same components under /demo (src/proxy.ts),
  // so a workspace link must go through useAppHref / useAppRouter / appRedirect
  // (lib/demo.ts) or one click takes a visitor out of the demo. This rule is
  // what keeps the demo in step with the app without anyone remembering it.
  {
    files: ["src/components/portal/**/*.{ts,tsx}", "src/app/app/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "Literal[value=/^\\/app(\\/|$|\\?|#)/]:not(CallExpression[callee.name=/^(appHref|appRedirect|toDemoPath)$/] > Literal):not(CallExpression[callee.property.name=/^(push|replace|prefetch|startsWith)$/] > Literal)",
          message:
            "Workspace links must stay inside the demo: wrap the href in appHref() (useAppHref) or navigate with useAppRouter().",
        },
        {
          selector:
            "TemplateLiteral[quasis.0.value.raw=/^\\/app(\\/|$|\\?|#)/]:not(CallExpression[callee.name=/^(appHref|appRedirect|toDemoPath)$/] > TemplateLiteral):not(CallExpression[callee.property.name=/^(push|replace|prefetch)$/] > TemplateLiteral)",
          message:
            "Workspace links must stay inside the demo: wrap the href in appHref() (useAppHref) or navigate with useAppRouter().",
        },
      ],
      "no-restricted-imports": [
        "error",
        {
          paths: [
            {
              name: "next/navigation",
              importNames: ["useRouter"],
              message: "Use useAppRouter() from @/components/demo/demo-context, so navigation stays inside the demo.",
            },
          ],
        },
      ],
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "backend/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
