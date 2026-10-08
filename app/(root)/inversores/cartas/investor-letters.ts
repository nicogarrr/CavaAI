import { authorKey, type LetterDoc } from "./letters";

// Explicit identities only. No substring matching (Munger is not Buffett).
const AUTHORS: Record<string, string[]> = {
  buffett: [
    "Warren E. Buffett (Berkshire Hathaway)",
    "Warren Buffett",
    "Berkshire Hathaway",
    "Buffett",
  ],
  quintana: [
    "Emérito Quintana (Numantia Patrimonio)",
    "Emerito Quintana",
    "Emérito Quintana",
    "Numantia",
    "Numantia Patrimonio Global",
  ],
  "terry-smith": ["Terry Smith", "Fundsmith"],
  ackman: ["Bill Ackman", "Pershing Square"],
  "nick-sleep": [
    "Nick Sleep",
    "Nick Sleep y Qais Zakaria",
    "Nomad Investment Partnership",
  ],
  "mark-leonard": ["Mark Leonard", "Constellation Software"],
  bezos: ["Jeff Bezos"],
  munger: ["Charlie Munger"],
  pabrai: ["Mohnish Pabrai"],
  klarman: ["Seth Klarman"],
};

export function investorLetters(
  slug: string,
  documents: LetterDoc[],
): LetterDoc[] {
  const aliases = new Set((AUTHORS[slug] ?? []).map(authorKey));
  return documents
    .filter(
      (doc) =>
        doc.document_type === "fund_letter" &&
        doc.status === "ready" &&
        doc.author &&
        aliases.has(authorKey(doc.author)),
    )
    .sort(
      (a, b) =>
        (b.publication_date ?? "").localeCompare(a.publication_date ?? "") ||
        b.title.localeCompare(a.title, "es"),
    );
}
