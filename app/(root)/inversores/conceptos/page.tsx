import type { Metadata } from "next";
import Link from "next/link";
import { CONCEPTS } from "./concepts";
import { Pagination, paginate } from "../_components/Pagination";

export const metadata: Metadata = { title: "Conceptos de inversión" };
export default async function ConceptsPage({
  searchParams,
}: {
  searchParams: Promise<{ pagina?: string }>;
}) {
  const { pagina } = await searchParams;
  const paged = paginate(CONCEPTS, pagina, 12);
  return (
    <main
      id="content"
      tabIndex={-1}
      className="mx-auto flex w-full min-w-0 max-w-5xl flex-col gap-8 overflow-x-clip py-6"
    >
      <h1 className="text-3xl font-semibold text-gray-100">Conceptos</h1>
      <ul className="grid min-w-0 grid-cols-1 gap-4 sm:grid-cols-2">
        {paged.items.map((concept) => (
          <li key={concept.slug}>
            <Link
              className="flex h-full flex-col gap-3 rounded-2xl border border-gray-800 bg-surface-1 p-6 hover:border-gray-600"
              href={`/inversores/conceptos/${concept.slug}`}
            >
              <h2 className="text-lg font-medium text-gray-100">
                {concept.title}
              </h2>
              <p className="text-sm text-gray-400">{concept.summary}</p>
              <span className="text-xs text-gray-500">
                {concept.source.title}
              </span>
            </Link>
          </li>
        ))}
      </ul>
      <Pagination
        basePath="/inversores/conceptos"
        page={paged.page}
        total={paged.total}
      />
    </main>
  );
}
