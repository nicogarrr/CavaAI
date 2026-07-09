import {
  E2E_ENABLED,
  E2E_SKIP_REASON,
  expect,
  jsonResponse,
  researchEvidencePdf,
  test,
  uniqueMarker,
} from "./fixtures/research-api";

type Ingestion = {
  status: string;
  document_id: number;
  chunks: number;
  parser: string;
};

type DocumentRecord = {
  id: number;
  title: string;
  chunks: Array<{ id: number; document_id: number; text: string }>;
};

type Claim = {
  id: number;
  status: string;
  evidence: Array<{
    document_id: number;
    document_chunk_id: number;
    evidence_type: string;
  }>;
};

type ResearchSession = { id: number };
type MemoryItem = { id: number; content: string; source_type: string };
type ChatResponse = {
  answer: string;
  sources: Array<{ type: string; id: number | string | null }>;
};

test.skip(!E2E_ENABLED, E2E_SKIP_REASON);

test("PDF upload -> chunk -> claim/evidence -> chat/memory", async ({ request }) => {
  const marker = uniqueMarker("e2e-evidence");
  const title = `MSFT evidence ${marker}`;

  const ingestion = await jsonResponse<Ingestion>(
    await request.post("/api/sources/documents/ingest-file", {
      multipart: {
        ticker: "MSFT",
        title,
        source_type: "sec_filing",
        source_url: `https://www.sec.gov/Archives/${marker}.pdf`,
        file: {
          name: `${marker}.pdf`,
          mimeType: "application/pdf",
          buffer: researchEvidencePdf(marker),
        },
      },
    }),
  );
  expect(ingestion).toMatchObject({
    status: "ingested",
    parser: "pypdf2",
  });
  expect(ingestion.chunks).toBeGreaterThan(0);

  const documents = await jsonResponse<DocumentRecord[]>(
    await request.get("/api/sources/documents", {
      params: { ticker: "MSFT", include_chunks: "true" },
    }),
  );
  const document = documents.find((candidate) => candidate.id === ingestion.document_id);
  expect(document).toBeDefined();
  expect(document?.title).toBe(title);
  expect(document?.chunks.length).toBeGreaterThan(0);
  const chunk = document?.chunks[0];
  if (!chunk) {
    throw new Error("The uploaded PDF did not produce a retrievable chunk.");
  }
  expect(chunk.text).toContain(marker);

  const claim = await jsonResponse<Claim>(
    await request.post("/api/memory/claims", {
      data: {
        ticker: "MSFT",
        statement: `Azure AI demand remains a durable growth driver (${marker}).`,
        claim_type: "growth_driver",
        materiality_score: 9,
        source_quality: "primary",
      },
    }),
  );
  expect(claim.status).toBe("unverified");

  await jsonResponse(
    await request.post(`/api/memory/claims/${claim.id}/evidence`, {
      data: {
        document_id: document?.id,
        document_chunk_id: chunk.id,
        source_url: `https://www.sec.gov/Archives/${marker}.pdf`,
        evidence_type: "supports",
        summary: `Primary PDF evidence supports the Azure demand claim (${marker}).`,
        quote: chunk.text,
        confidence: 0.95,
        source_tier: "tier_1_regulatory",
      },
    }),
  );

  const supportedClaim = await jsonResponse<Claim>(
    await request.get(`/api/memory/claims/${claim.id}`),
  );
  expect(supportedClaim.status).toBe("supported");
  expect(supportedClaim.evidence).toContainEqual(
    expect.objectContaining({
      document_id: ingestion.document_id,
      document_chunk_id: chunk.id,
      evidence_type: "supports",
    }),
  );

  const session = await jsonResponse<ResearchSession>(
    await request.post("/api/memory/research-sessions", {
      data: {
        ticker: "MSFT",
        title: `Evidence review ${marker}`,
        question: `Does the uploaded evidence support Azure demand (${marker})?`,
        source_ids: [ingestion.document_id],
        claim_ids: [claim.id],
      },
    }),
  );
  const memory = await jsonResponse<MemoryItem>(
    await request.post("/api/memory/memory-items", {
      data: {
        ticker: "MSFT",
        research_session_id: session.id,
        scope: "company",
        memory_type: "watch_item",
        importance: 9,
        content: `Track Azure AI demand and the primary evidence marker ${marker}.`,
        source_type: "user",
        source_id: ingestion.document_id,
      },
    }),
  );

  const chat = await jsonResponse<ChatResponse>(
    await request.post("/api/chat", {
      data: {
        ticker: "MSFT",
        scope: "company",
        question: `Remember ${marker}; what evidence supports the Azure AI demand claim?`,
      },
    }),
  );
  const sourceTypes = new Set(chat.sources.map((source) => source.type));
  expect([...sourceTypes]).toEqual(
    expect.arrayContaining(["claim", "claim_evidence", "document_chunk", "memory_item"]),
  );
  expect(chat.sources).toContainEqual(
    expect.objectContaining({ type: "memory_item", id: memory.id }),
  );
  expect(chat.sources).toContainEqual(expect.objectContaining({ type: "memory_writeback" }));
  expect(chat.answer).toContain(marker);

  const memories = await jsonResponse<MemoryItem[]>(
    await request.get("/api/memory/memory-items", {
      params: { ticker: "MSFT", scope: "company" },
    }),
  );
  expect(memories).toContainEqual(expect.objectContaining({ id: memory.id }));
  expect(memories).toContainEqual(
    expect.objectContaining({ source_type: "chat", content: expect.stringContaining(marker) }),
  );
});
