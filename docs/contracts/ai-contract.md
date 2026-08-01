# AI Contract

## Ownership

- The AI service owns semantic understanding, retrieval, and model-driven responses.
- It operates on embeddings, catalogue metadata, and content chunks.

## Inputs

- catalogue public IDs and metadata
- content embeddings and chunk metadata
- user queries and session context

## Outputs

- semantic search results
- read-mode summaries
- CBT question suggestions
- relevance scores and evidence references

## APIs

AI APIs should expose:
- `POST /ai/query`
- `POST /ai/retrieve`
- `POST /ai/generate`
- `GET /ai/status`

## Events

AI services may publish:
- `ai.embedding.created`
- `ai.retrieval.performed`
- `ai.result.generated`

## Service boundaries

- The AI service does not own canonical catalogue or content truth.
- It consumes catalogue and content contracts to produce semantic results.
