-- 001_quote.sql
-- DDL for the quotes table — maps from scripts/lib/quote.py QuoteObject.
-- Idempotent: uses IF NOT EXISTS on all CREATE statements.

CREATE TABLE IF NOT EXISTS quotes (
    quote_id        TEXT     PRIMARY KEY,
    text            TEXT     NOT NULL,
    edition_id      TEXT     NOT NULL,
    year            INTEGER  NOT NULL CHECK (year BETWEEN 1979 AND 2100),
    revision_num    INTEGER  NOT NULL CHECK (revision_num BETWEEN 0 AND 30),
    quote_type      TEXT     NOT NULL CHECK (quote_type IN (
                        'narrative', 'definition', 'checklist',
                        'principle', 'example', 'procedure'
                    )),
    section_path    TEXT     NOT NULL DEFAULT '[]',
    start_line      INTEGER  NOT NULL CHECK (start_line >= 1),
    char_span_start INTEGER  NOT NULL CHECK (char_span_start >= 0),
    char_span_end   INTEGER  NOT NULL CHECK (char_span_end >= char_span_start),
    token_count     INTEGER  NOT NULL DEFAULT 0,
    content_hash    CHAR(64) NOT NULL UNIQUE,
    quality_flags   TEXT     NOT NULL DEFAULT '[]',
    is_definition   BOOLEAN  NOT NULL DEFAULT 0,
    created_at      TEXT     NOT NULL DEFAULT (datetime('now'))
);

-- Lookup indexes
CREATE INDEX IF NOT EXISTS idx_quotes_edition      ON quotes(edition_id);
CREATE INDEX IF NOT EXISTS idx_quotes_year          ON quotes(year);
CREATE INDEX IF NOT EXISTS idx_quotes_type          ON quotes(quote_type);
CREATE INDEX IF NOT EXISTS idx_quotes_content_hash  ON quotes(content_hash);
CREATE INDEX IF NOT EXISTS idx_quotes_definition    ON quotes(is_definition) WHERE is_definition = 1;
