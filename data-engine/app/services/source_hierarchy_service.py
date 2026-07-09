from dataclasses import dataclass


@dataclass(frozen=True)
class SourceTier:
    key: str
    label: str
    rank: int
    trust_score: float
    policy: str


SOURCE_TIERS: dict[str, SourceTier] = {
    "tier_1_regulatory": SourceTier(
        key="tier_1_regulatory",
        label="Regulatory filing",
        rank=1,
        trust_score=1.0,
        policy="Primary regulatory evidence. Prefer this over vendor or media conflicts.",
    ),
    "tier_2_company": SourceTier(
        key="tier_2_company",
        label="Company primary",
        rank=2,
        trust_score=0.9,
        policy="Primary company evidence. Use for thesis updates, but reconcile against filings when numbers conflict.",
    ),
    "tier_3_transcript": SourceTier(
        key="tier_3_transcript",
        label="Transcript or call",
        rank=3,
        trust_score=0.82,
        policy="Management commentary. Treat forward-looking statements as claims until confirmed by results.",
    ),
    "tier_4_reputable_media": SourceTier(
        key="tier_4_reputable_media",
        label="Reputable media",
        rank=4,
        trust_score=0.72,
        policy="Useful alert source. Do not change model assumptions without primary-source confirmation.",
    ),
    "tier_5_data_provider": SourceTier(
        key="tier_5_data_provider",
        label="Data provider",
        rank=5,
        trust_score=0.68,
        policy="Useful normalized data. Reconcile important conflicts against SEC/company primary sources.",
    ),
    "tier_6_bootstrap": SourceTier(
        key="tier_6_bootstrap",
        label="Bootstrap seed",
        rank=6,
        trust_score=0.45,
        policy="Startup data only. Replace with primary evidence before final thesis decisions.",
    ),
    "tier_7_user_input": SourceTier(
        key="tier_7_user_input",
        label="User input",
        rank=7,
        trust_score=0.38,
        policy="User-provided evidence or assumption. Keep it visible and confirm before material model changes.",
    ),
    "tier_unknown": SourceTier(
        key="tier_unknown",
        label="Unknown source",
        rank=99,
        trust_score=0.25,
        policy="Unknown reliability. Store as context only until source quality is established.",
    ),
}


SOURCE_TIER_BY_TYPE = {
    "sec": "tier_1_regulatory",
    "sec_edgar": "tier_1_regulatory",
    "edgar": "tier_1_regulatory",
    "filing": "tier_1_regulatory",
    "10-k": "tier_1_regulatory",
    "10-q": "tier_1_regulatory",
    "20-f": "tier_1_regulatory",
    "8-k": "tier_1_regulatory",
    "company_ir": "tier_2_company",
    "investor_relations": "tier_2_company",
    "earnings_release": "tier_2_company",
    "shareholder_letter": "tier_2_company",
    "earnings_call": "tier_3_transcript",
    "transcript": "tier_3_transcript",
    "quartr": "tier_3_transcript",
    "reuters": "tier_4_reputable_media",
    "bloomberg": "tier_4_reputable_media",
    "wsj": "tier_4_reputable_media",
    "ft": "tier_4_reputable_media",
    "fmp": "tier_5_data_provider",
    "finnhub": "tier_5_data_provider",
    "yahoo": "tier_5_data_provider",
    "company_master_seed": "tier_6_bootstrap",
    "seed": "tier_6_bootstrap",
    "manual": "tier_7_user_input",
    "manual_upload": "tier_7_user_input",
    "chat": "tier_7_user_input",
    "user": "tier_7_user_input",
}


def classify_source(source_type: str | None = None, url: str | None = None) -> SourceTier:
    compact_type = (source_type or "").lower().replace(" ", "_")
    for key, tier_key in SOURCE_TIER_BY_TYPE.items():
        if key in compact_type:
            return SOURCE_TIERS[tier_key]

    compact_url = (url or "").lower()
    if "sec.gov" in compact_url or "edgar" in compact_url:
        return SOURCE_TIERS["tier_1_regulatory"]
    if "/investor" in compact_url or "ir." in compact_url:
        return SOURCE_TIERS["tier_2_company"]
    for media_key in ("reuters", "bloomberg", "wsj", "ft.com"):
        if media_key in compact_url:
            return SOURCE_TIERS["tier_4_reputable_media"]

    return SOURCE_TIERS["tier_unknown"]


def source_tier_key(source_type: str | None = None, url: str | None = None) -> str:
    return classify_source(source_type, url).key
