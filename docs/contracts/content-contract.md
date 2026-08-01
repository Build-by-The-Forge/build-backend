# Content Contract

## Ownership

- Academic Content owns learning resources and educational material.
- This includes books, PDFs, videos, slides, exercises, and other instructional assets.

## Relationship to Catalogue

- Content may be linked to catalogue entities such as course codes, topic slugs, or curriculum versions.
- Content does not own the academic definitions of those catalogue entities.

## Public IDs

- Content assets should have stable public IDs or slugs for retrieval.
- Metadata such as ISBN, DOI, or external URLs may be used for reference.

## APIs

Content APIs should expose:
- listing and lookup of learning resources
- metadata retrieval
- associations to catalogue entities

## Events

Content services can publish events such as:
- `content.asset.ingested`
- `content.asset.updated`
- `content.asset.tagged`
- `content.asset.deleted`

## Service boundaries

- Academic Content is responsible for ingestion, OCR, cleaning, chunking, and material metadata.
- It should not model course curricula or learning outcomes directly.
