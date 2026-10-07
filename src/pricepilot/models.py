"""Database schema.

Phase 0 creates only the tables that Phases 0-2 actually write to, plus the two
operational tables that CLAUDE.md §5 requires from day one (`scrape_runs`, `llm_calls`).
Tables for matching, demand and recommendations are added in their own phases so that
migrations stay small and reviewable. See DECISIONS.md ADR-0004.

Money is `Numeric(12, 2)` everywhere. Never float — CLAUDE.md §6 guardrails compare
margins and a float rounding error there is a real bug.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, validates


class Base(DeclarativeBase):
    pass


class Product(Base):
    """Our own catalogue, mirrored from services/mock_store.

    The mock store is the system of record (it stands in for Shopify/WooCommerce);
    this table is the pipeline's local copy so joins do not require an HTTP call.
    """

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    brand: Mapped[str] = mapped_column(String(128), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    purchase_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    current_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    stock: Mapped[int] = mapped_column(Integer, default=0)
    # Matcher key signal (same line at a different gramaj is a different product). NULL for
    # grooming / accessories. Added by migration 0011, ADR-0038.
    net_weight_g: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProductMatch(Base):
    """Phase 5 session 3b -- OUR product matched to a competitor listing (ADR-0039, migration 0012).

    Grain: one row per (our product, competitor shop) -- the unique constraint enforces "at most
    one match per (product, shop), highest score wins". The price is the matched shop listing's
    latest observation from `raw_listings` (`external_id` + `price_date` say which), a SQL number,
    never retrieved by similarity. `score` is rounded DOWN to 6 places and `threshold` is stored per
    row, so `score >= threshold` holds exactly (CHECK).
    """

    __tablename__ = "product_matches"
    __table_args__ = (
        UniqueConstraint("product_id", "source", name="uq_product_matches_product_source"),
        CheckConstraint("score >= threshold", name="ck_product_matches_score_ge_threshold"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(64))
    norm_listing_id: Mapped[int] = mapped_column(ForeignKey("norm_listings.id", ondelete="CASCADE"))
    content_hash: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(Text)
    competitor_title: Mapped[str] = mapped_column(Text)
    score: Mapped[Decimal] = mapped_column(Numeric(7, 6))
    threshold: Mapped[Decimal] = mapped_column(Numeric(7, 6))
    model_sha256: Mapped[str] = mapped_column(String(64))
    competitor_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    price_date: Mapped[date] = mapped_column(Date)
    in_stock: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Recommendation(Base):
    """Phase 5 session 4 -- the full trace of ONE price recommendation (ADR-0042, migration 0013).

    CLAUDE.md section 6 rule 6: every LLM decision is traced -- the input snapshot (numbers from
    SQL / `config/pricing-policy.toml`), the retrieved policy sections, the prompt, the raw reply,
    latency, cost, and what the deterministic guard did with the proposal. `is_mock` is TRUE for
    rows written by the mock proposer: they cost $0, never touched `llm_calls`, and must never be
    counted toward the Phase 5 gate. Money is `Numeric(12, 2)`; JSON money is stored as strings.
    """

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    run_label: Mapped[str] = mapped_column(String(64), index=True)
    is_mock: Mapped[bool] = mapped_column(Boolean)
    # NULL = the product's real, unperturbed inputs. s5 may set a named scenario (ADR-0042).
    scenario: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # --- input snapshot: what the proposer and the guard were given ---
    category: Mapped[str] = mapped_column(String(64))
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    current_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    stock: Mapped[int] = mapped_column(Integer)
    # [{"shop", "price", "score", "price_date", "in_stock", "title"}...]; empty list = no matched competitor.
    competitor_prices: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    price_7d_ago: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    # The mock store's history is SYNTHETIC; this says so on every row.
    price_7d_ago_source: Mapped[str] = mapped_column(String(64))
    # A labelled PLACEHOLDER (Phase 4 POSTPONE) -- never a measured or recovered elasticity.
    elasticity_placeholder: Mapped[dict[str, Any]] = mapped_column(JSON)

    # --- retrieval + prompt + reply ---
    rag_sections: Mapped[list[dict[str, Any]]] = mapped_column(JSON)  # section_ref + similarity
    prompt_text: Mapped[str] = mapped_column(Text)
    llm_model: Mapped[str] = mapped_column(String(64))  # "mock" for the mock proposer
    llm_raw_reply: Mapped[str] = mapped_column(Text)
    # NULL when the reply could not be parsed (the guard is then not consulted: FLAG).
    llm_proposed_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    llm_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    llm_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The provider's stop_reason ("end_turn", "max_tokens", ...); a "max_tokens" reply is cut off and
    # is never trusted (migration 0014). NULL for mock rows and for rows written before 0014.
    llm_stop_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # --- the guard's verdict: the final authority on the applied price ---
    guard_status: Mapped[str] = mapped_column(String(16))  # APPROVE | REJECT | FLAG
    guard_final_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    guard_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "guard_status IN ('APPROVE', 'REJECT', 'FLAG')", name="ck_recommendations_guard_status"
        ),
        # An applied price exists exactly when the guard APPROVEd.
        CheckConstraint(
            "(guard_status = 'APPROVE') = (guard_final_price IS NOT NULL)",
            name="ck_recommendations_final_price_iff_approve",
        ),
    )


class ActionLog(Base):
    """Phase 6 -- one row per action taken on a recommendation (ADR-0047, migration 0015).

    `update_price` writes a guard-APPROVEd price to the store; `rollback` reverts one;
    `flag_for_review` / `do_nothing` record that nothing was written (and why). `reverted_by` points
    at the `rollback` row that undid an `update_price`. A partial unique index allows only ONE live
    `update_price` per recommendation: the database refuses a double apply.
    """

    __tablename__ = "action_log"
    __table_args__ = (
        CheckConstraint(
            "action IN ('update_price', 'flag_for_review', 'do_nothing', 'rollback')",
            name="ck_action_log_action",
        ),
        CheckConstraint(
            "(action IN ('update_price', 'rollback')) = (new_price IS NOT NULL)",
            name="ck_action_log_new_price_iff_write",
        ),
        CheckConstraint(
            "reverted_by IS NULL OR action = 'update_price'",
            name="ck_action_log_reverted_is_update",
        ),
        Index(
            "uq_action_log_one_live_update",
            "recommendation_id",
            unique=True,
            postgresql_where=text("action = 'update_price' AND reverted_by IS NULL"),
            sqlite_where=text("action = 'update_price' AND reverted_by IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("recommendations.id", ondelete="RESTRICT"), index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(24))
    previous_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    new_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Position of the matching entry in the store's in-memory /audit-log (it has no ids and resets
    # when the store process restarts), e.g. "audit-log[3]"; "UNVERIFIED" if the write could not be
    # matched afterwards. NULL for actions that wrote nothing.
    mock_store_audit_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reverted_by: Mapped[int | None] = mapped_column(
        ForeignKey("action_log.id", ondelete="RESTRICT"), nullable=True
    )


class ScrapeRun(Base):
    """One execution of one source adapter. CLAUDE.md §5.6: every run is logged,
    and a >40% drop in items vs the previous run raises an alert instead of ingesting."""

    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(nullable=True)
    items_found: Mapped[int] = mapped_column(Integer, default=0)
    items_ingested: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    # "ok" | "running" | "failed" | "volume_alert"
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The actual error strings (capped — see runner.py), not just the `errors` count above.
    # Session note (2026-09-12): a bare count was un-diagnosable after the fact, twice.
    error_detail: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    listings: Mapped[list[RawListing]] = relationship(back_populates="run")


class RawListing(Base):
    """A competitor listing exactly as scraped. Append-only **across days**: one row per
    (listing, day), because the price time series *is* the data Phase 4 needs and cannot be
    backfilled. **Idempotent within a day**: a manual run and the scheduled run on the same
    calendar day upsert the same row on (source, external_id, collected_date) rather than
    duplicating it — STEP 4, ADR-0016, amending ADR-0005's original one-row-per-run design.
    """

    __tablename__ = "raw_listings"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "external_id",
            "collected_date",
            name="uq_raw_listings_source_external_collected_date",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("scrape_runs.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(64), index=True)
    # The shop's own internal id. Useless across shops (CLAUDE.md §7 Phase 1) but the
    # only stable handle *within* a shop, so it anchors the time series.
    source_product_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    # `source_product_id` when the shop has one, else the listing URL — the same fallback the
    # petmax adapter already uses to dedupe within one run (ADR-0016). Half of the idempotency
    # key: (source, external_id, collected_date) is unique, enforced by the constraint above.
    external_id: Mapped[str] = mapped_column(String(255), index=True)
    # The calendar day this observation belongs to (the run's start date, not scraped_at's
    # exact timestamp) — the other half of the idempotency key.
    collected_date: Mapped[date] = mapped_column(Date)
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(8), default="RON")
    # Pre-discount price where the shop exposes one; drives promotion detection in Phase 4.
    compare_at_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    in_stock: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # `none_as_null=True`: SQLAlchemy's JSON type otherwise persists a Python `None` as the JSON
    # literal `null`, not SQL NULL (ADR-0032) -- every `IS NULL`/`IS NOT NULL` check the dedup
    # feature relies on (`get_payload`, the callers routed through it) needs a real SQL NULL.
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    # sha256 of the canonical (sort_keys) JSON of raw_payload -- ADR-0032/0009 migration. Set on
    # every row from this migration on, whether or not raw_payload itself is NULL: it is what
    # ingest compares the next day's payload against, and what `get_payload()` uses to prove a
    # NULL payload really was a duplicate rather than data loss. Legacy pre-migration rows carry
    # NULL here permanently (no backfill in this session) and are treated as "no previous hash"
    # by the ingest comparison, i.e. the day after deploy always stores its payload in full.
    raw_payload_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    # sha256 of the normalized title. Phase 2 caches attribute extraction on this so the
    # LLM never re-runs on an unchanged title (CLAUDE.md §5 — largest cost risk).
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    # NULL = in scope. Non-NULL = quarantined: names the signal that fired (e.g.
    # "title_token:vd", "product_type:diete veterinare pentru caini"), never a boolean, so the
    # reason is inspectable without a second lookup. Reversible by design (ADR-0025): clearing
    # this column restores the row to every count and query that filters on it — nothing is
    # ever deleted for a regulated-product finding.
    #
    # This column exists for rows collected *before* the tightened is_regulated()/product_type
    # check existed (ADR-0025) — a one-off backfill (scripts/quarantine_regulated.py), never
    # written by a scraper directly. Going forward, a regulated item is still filtered before
    # insertion, exactly as before ADR-0025 — the tightened check just catches more of them — so
    # a *new* row normally never needs this column at all; it stays populated only for the
    # historical backfill and for any future manual quarantine of something the ingest-time
    # check still misses.
    excluded_reason: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)

    run: Mapped[ScrapeRun] = relationship(back_populates="listings")


Index("ix_raw_listings_source_scraped", RawListing.source, RawListing.scraped_at)


class NormListing(Base):
    """Phase 2 — attributes extracted from a normalized title (CLAUDE.md §6/§7, ADR-0026).

    **Keyed on `content_hash`, not on `raw_listings.id`.** `content_hash` (reused from
    `RawListing.content_hash` — see `Listing.content_hash` in scrapers/base.py) is
    `sha256(normalize_title(title))`: title only, no price/stock/source. Verified before this
    table was built (ADR-0026), because reusing it *without* checking would have silently broken
    CLAUDE.md §5.1/§9: if it carried anything that changes day to day, this table would grow a
    new row every time a price moved and re-extract on every unchanged title. It doesn't, so one
    row here serves every `raw_listings` row that ever shares this exact normalized title —
    **across sources as well as across days** (ADR-0026: deliberately global, not
    per-(source, content_hash) — the key already contains no source component, and an identical
    normalized title from two independently-run shops overwhelmingly means the same real product
    with the same real attributes, not a coincidence worth paying to re-extract).

    **Every extracted field is nullable, and "not stated" is not the same claim as "extraction
    failed"** (this session's explicit schema requirement). A null `brand` with no `"brand"` key
    in `extraction_errors` means the title genuinely names no brand. A null `brand` **with** a
    `"brand"` key in `extraction_errors` means the extractor raised on this title and the null is
    a gap, not an answer. Never conflate the two when reading this table.

    Never written to by a scraper. Never read by `overlap.py`, which stays frozen (CLAUDE.md §7
    Phase 1 gate — an independent measurement, not this table's consumer).
    """

    __tablename__ = "norm_listings"
    __table_args__ = (
        # ADR-0026: a listing's quantity is mass-based XOR volume-based, never both — a bag of
        # kibble has no stated volume and a bottle of shampoo has no stated weight. Written in
        # plain boolean form (not Postgres's `num_nonnulls()`) so the same constraint is
        # enforceable and testable against SQLite in-memory too, with no live database needed.
        # Both NULL is allowed and means "quantity not stated in the title" — a legitimate value,
        # not a violation.
        CheckConstraint(
            "NOT (net_weight_g IS NOT NULL AND net_volume_ml IS NOT NULL)",
            name="ck_norm_listings_weight_xor_volume",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # The cache key. Unique: one row per unique normalized title, full stop (ADR-0026).
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # One representative raw_listings row this hash was extracted from — content_hash itself
    # isn't reversible, and the extractor needs real text, not just its digest.
    sample_source: Mapped[str] = mapped_column(String(64))
    sample_title: Mapped[str] = mapped_column(Text)

    brand: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    product_line: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Grams-equivalent, single purchasable unit — STEP 2 convention 1: "12x85 g" stores 85 here,
    # not the 1,020 g total; convention 3: "1 x 85 g" also stores 85. Convention 4: an animal's
    # dosage band ("10-25 kg") must NEVER populate this field — see `dosage_band` below.
    net_weight_g: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Sibling of net_weight_g for liquid products (shampoo, supplements) — overlap_key() already
    # treats ml/l as a weight-equivalent (ADR-0021's water-density proxy) for its own floor-metric
    # purposes, but Phase 2's normalized layer keeps volume and mass as distinct, honestly-typed
    # fields rather than silently reusing that proxy as if it were exact.
    net_volume_ml: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # STEP 2 convention 1/3: pack count, e.g. "12x85 g" -> 12, "1 x 85 g" -> 1.
    pack_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # STEP 2 convention 2: "12+2 kg" -> base net_weight_g=12000, bonus_weight_g=2000, recorded
    # separately. Reuses OverlapKey.bonus_g's existing semantics exactly (ADR-0021) — not a second,
    # conflicting convention. NULL = no bonus pattern in the title (a real, expected answer).
    bonus_weight_g: Mapped[int | None] = mapped_column(Integer, nullable=True)
    breed_size_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    life_stage: Mapped[str | None] = mapped_column(String(16), nullable=True)
    flavour: Mapped[str | None] = mapped_column(String(64), nullable=True)
    food_form: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # STEP 2 convention 4: raw text, e.g. "10-25 kg" — the ANIMAL's weight, never the product's.
    # Kept as text rather than split into min/max (approved this session): the gate needs the
    # value correct and distinguishable, not range-queryable; a min/max split is derivable later
    # from this text without re-extraction if a later phase needs it.
    dosage_band: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # "ok" | "error" — row-level outcome. "error" means at least one field is in
    # extraction_errors below; it does not by itself say the whole row is unusable.
    extraction_status: Mapped[str] = mapped_column(String(16), default="ok")
    # {field_name: error message} — populated ONLY for a field where the extractor raised.
    # Never populated for a field that is null because the title simply doesn't state it — that
    # is normal output, not an error, and recording it here would erase the distinction this
    # table exists to preserve.
    extraction_errors: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    # Bumped when extraction logic changes materially, so a future session can decide whether
    # existing rows need re-extraction (free to re-run — deterministic, no LLM spend — but still
    # worth knowing which rows predate a rule change).
    extractor_version: Mapped[str] = mapped_column(String(32))
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Phase 3 STEP 2 (candidate retrieval), migration 0006. 384-dim
    # paraphrase-multilingual-MiniLM-L12-v2, computed by `scripts/build_embeddings.py` from
    # `f"{brand} {product_line or sample_title}"` — never inline in `extract()`, which stays
    # LLM/network-free. NULL until that batch job runs on a row.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)

    # Phase 3 STEP 3 signals (migration 0007) — `scripts/backfill_phase3_signals.py` populates
    # all three from `raw_listings`/`brand`, never `extract()` (needs `url`/`raw_payload`, which
    # the title-only deterministic pipeline deliberately never reads).
    # "food" | "accessory" | "litter" | "toy" | NULL (`normalize.category.categorize_listing`).
    category: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    # Hyphen/space/punctuation-insensitive form of `brand`, for candidate BLOCKING — never for
    # display (`normalize.brand.brand_blocking_key`).
    brand_blocking_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    # True only for the small, hand-verified list in `normalize.brand.is_suspected_distributor_code`
    # — never a statistical threshold (see that function's own docstring for why one was rejected).
    brand_is_distributor_code: Mapped[bool] = mapped_column(Boolean, default=False)

    # Phase 3 finding 4 (2026-09-15 session, reference labelling pass), migration 0008 — same
    # backfill pattern as the three signals above (`normalize.species.classify_species`, needs
    # `url`/`raw_payload`/`category`, never `extract()`). "dog" | "cat" | NULL.
    species: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    # Phase 3 finding 5 (same session), migration 0008 — `normalize.attributes.breed_size_class`,
    # a rank-interval canonicalisation of `breed_size_code` packed as `"lo-hi"` (e.g. `"3-3"` for
    # "M"/"Medium", `"1-2"` for "Mini"/"XS-S"), same shape/purpose as `brand_blocking_key`: a
    # derived lookup column for candidate blocking, never a replacement for the raw token.
    # Computed from `breed_size_code` alone (title-only lineage), so this one IS safe to compute
    # in `extract()` — but is backfilled alongside the other three for one consistent script.
    breed_size_class: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)

    @validates("net_weight_g", "net_volume_ml")
    def _validate_weight_xor_volume(self, key: str, value: int | None) -> int | None:
        """Same invariant as `ck_norm_listings_weight_xor_volume`, enforced in-process so a
        violation raises `ValueError` on assignment — offline-testable with no database at all,
        and a second line of defence alongside the DB constraint (never a substitute for it: the
        constraint is what protects a future write path that bypasses the ORM)."""
        other = "net_volume_ml" if key == "net_weight_g" else "net_weight_g"
        if value is not None and getattr(self, other, None) is not None:
            raise ValueError(
                f"NormListing cannot have both net_weight_g and net_volume_ml set "
                f"(setting {key}={value!r} while {other} is already set)"
            )
        return value


class PolicyChunk(Base):
    """Phase 5 session 2 -- RAG index over the pricing-policy prose (ADR-0036, migration 0010).

    Text only. CLAUDE.md section 6, hard architectural rule 1: every number a recommendation acts
    on comes from SQL or `config/pricing-policy.toml`, never retrieved by similarity here. This
    table exists so the decision engine (session 3) can hand the LLM the relevant policy
    paragraphs; it is never a source of a threshold.

    One row per policy section (`section_ref` is the upsert key `scripts/build_policy_index.py`
    keys on), not one row per version -- re-indexing an edited policy document replaces a
    section's row in place. `doc_version`/`source_sha256` say which version of
    `docs/policy/pricing-policy.md` produced the row currently stored.
    """

    __tablename__ = "policy_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    section_ref: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    heading: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    # Same model/dim as NormListing.embedding (paraphrase-multilingual-MiniLM-L12-v2, 384) -- the
    # index and the query MUST use the same model or cosine similarity is meaningless.
    embedding: Mapped[list[float]] = mapped_column(Vector(384))
    source_doc: Mapped[str] = mapped_column(String(255))
    doc_version: Mapped[str] = mapped_column(String(32))
    source_sha256: Mapped[str] = mapped_column(String(64))


class LlmCall(Base):
    """Every LLM call, logged by src/pricepilot/llm/client.py. No direct SDK calls exist
    anywhere else in the codebase — ruff enforces it (see pyproject.toml)."""

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    phase: Mapped[str] = mapped_column(String(32), index=True)
    purpose: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(64), index=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    # Content hash of the request. A cache hit is recorded with cost 0 so `make cost`
    # shows what caching actually saved.
    cache_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
