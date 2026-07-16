import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const eslintConfig = [
  ...nextVitals,
  ...nextTypescript,
  {
    ignores: [
      "node_modules/**",
      ".next/**",
      ".next-e2e/**",
      "playwright-report/**",
      "test-results/**",
      "data-engine/.pytest_cache/**",
      "data-engine/.venv/**",
      "data-engine/**/__pycache__/**",
      "data-engine/**/*.py",
      "data-engine/**/*.html",
      "data-engine/**/*.db",
      "data-engine/storage/**",
      "out/**",
      "build/**",
      "dist/**",
      "next-env.d.ts",
      "**/*.d.ts",
      "**/*.config.*",
    ],
  },
  {
    rules: {
      "@typescript-eslint/no-explicit-any": "warn",
      "react-hooks/error-boundaries": "warn",
      "react-hooks/purity": "warn",
      "react-hooks/set-state-in-effect": "warn",
      "react/no-unescaped-entities": "warn",
    },
  },
];

export default eslintConfig;
