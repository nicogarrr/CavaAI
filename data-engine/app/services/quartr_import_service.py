from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, Document, DocumentChunk, Transcript


class QuartrImportService:
    def import_text(
        self,
        db: Session,
        ticker: str,
        title: str,
        text: str,
        source_url: str | None = None,
        period: str = "unknown",
    ) -> dict:
        company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
        if not company:
            raise ValueError(f"Unknown ticker: {ticker}")

        document = Document(
            company_id=company.id,
            title=title,
            source_type="quartr_manual",
            source_url=source_url,
            published_at=datetime.now(UTC),
            metadata_={
                "source_app": "Quartr",
                "ingestion_mode": "manual_export_or_copy_paste",
                "official_api": False,
            },
        )
        db.add(document)
        db.flush()

        chunk_size = 3500
        chunks = [text[index : index + chunk_size] for index in range(0, len(text), chunk_size)]
        for index, chunk in enumerate(chunks):
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=index,
                    text=chunk,
                    token_count=max(1, len(chunk) // 4),
                    metadata_={"ticker": company.ticker, "source_type": "quartr_manual"},
                )
            )

        transcript = Transcript(
            company_id=company.id,
            title=title,
            period=period,
            source_id=document.id,
            transcript_text=text,
        )
        db.add(transcript)
        db.commit()
        db.refresh(document)

        return {
            "document_id": document.id,
            "transcript_id": transcript.id,
            "ticker": company.ticker,
            "chunks": len(chunks),
            "source_type": "quartr_manual",
        }

