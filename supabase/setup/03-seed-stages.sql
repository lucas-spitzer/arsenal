-- Foundry fresh setup: stage definitions (current names, schemas, and prompts).
-- Uses ON CONFLICT upserts so re-running is safe. For repairing an existing
-- project's stages table, prefer restore-stages.sql (identical upserts).

insert into public.stages (
  stage_id,
  version,
  module,
  name,
  description,
  modalities,
  input_schema,
  output_schema,
  prompts
)
values
  (
    'parse',
    '1.0',
    'intellex',
    'Parse Document',
    'Parse PDF sources into structured lines via the LlamaParse API.',
    array['text'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"filename":{"type":"string"},"mime_type":{"type":"string"},"file_size_bytes":{"type":"integer"}}}'::jsonb,
    '{
      "type": "object",
      "required": ["page_count", "line_count", "parser", "api_response"],
      "properties": {
        "summary": {"type": "string"},
        "page_count": {"type": "integer"},
        "line_count": {"type": "integer"},
        "parser": {"type": "string"},
        "job_id": {"type": "string"},
        "raw_markdown_path": {"type": "string"},
        "api_response": {"type": "object"}
      }
    }'::jsonb,
    '{
      "system": "Parse uploaded PDF sources into page-aware markdown and normalized document lines.",
      "user_template": "Parse source {{source_id}} ({{filename}})."
    }'::jsonb
  ),
  (
    'normalize-document',
    '1.0',
    'intellex',
    'Normalize Document',
    'Flatten LlamaParse structured pages into reading-order elements, dropping page furniture.',
    array['text'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"page_count":{"type":"integer"}}}'::jsonb,
    '{"type":"object","properties":{"element_count":{"type":"integer"},"dropped_furniture":{"type":"object"}}}'::jsonb,
    '{"system":"Normalize LlamaParse structured layout into a flat element stream.","user_template":"Normalize source {{source_id}}."}'::jsonb
  ),
  (
    'normalize-document',
    '1.1',
    'intellex',
    'Normalize Document',
    'Flatten LlamaParse structured pages into reading-order elements, preserving compact layout provenance and dropping page furniture.',
    array['text'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"page_count":{"type":"integer"}}}'::jsonb,
    '{"type":"object","properties":{"element_count":{"type":"integer"},"dropped_furniture":{"type":"object"}}}'::jsonb,
    '{"system":"Normalize LlamaParse structured layout into a provenance-aware flat element stream.","user_template":"Normalize source {{source_id}}."}'::jsonb
  ),
  (
    'trim-document-boundaries',
    '1.0',
    'intellex',
    'Trim Document',
    'Detect and trim front/back matter before the first chapter and after back-matter markers.',
    array['text'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"element_count":{"type":"integer"}}}'::jsonb,
    '{"type":"object","properties":{"start_index":{"type":"integer"},"end_index":{"type":"integer"},"kept_element_count":{"type":"integer"},"boundary_reasons":{"type":"object"}}}'::jsonb,
    '{"system":"Trim non-body front and back matter from normalized elements.","user_template":"Trim boundaries for source {{source_id}}."}'::jsonb
  ),
  (
    'structure-document',
    '1.0',
    'intellex',
    'Structure Document',
    'Classify trimmed elements into chapters, sections, and body paragraphs.',
    array['text'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"element_count":{"type":"integer"}}}'::jsonb,
    '{"type":"object","properties":{"chapter_count":{"type":"integer"},"section_count":{"type":"integer"},"chapter_titles":{"type":"array"},"dropped_nontext":{"type":"object"}}}'::jsonb,
    '{"system":"Build a chapter/section Book model from trimmed elements.","user_template":"Structure source {{source_id}}."}'::jsonb
  ),
  (
    'structure-document',
    '1.1',
    'intellex',
    'Structure Document',
    'Classify trimmed elements into chapters, sections, and body paragraphs; rejoins figure-spanning sentences.',
    array['text'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"element_count":{"type":"integer"}}}'::jsonb,
    '{"type":"object","properties":{"chapter_count":{"type":"integer"},"section_count":{"type":"integer"},"chapter_titles":{"type":"array"},"dropped_nontext":{"type":"object"}}}'::jsonb,
    '{"system":"Build a chapter/section Book model from trimmed elements.","user_template":"Structure source {{source_id}}."}'::jsonb
  ),
  (
    'structure-document',
    '1.2',
    'intellex',
    'Structure Document',
    'Classify trimmed elements into chapters, sections, and body paragraphs; preserves epigraph quote/attribution spacing.',
    array['text'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"element_count":{"type":"integer"}}}'::jsonb,
    '{"type":"object","properties":{"chapter_count":{"type":"integer"},"section_count":{"type":"integer"},"chapter_titles":{"type":"array"},"dropped_nontext":{"type":"object"}}}'::jsonb,
    '{"system":"Build a chapter/section Book model from trimmed elements.","user_template":"Structure source {{source_id}}."}'::jsonb
  ),
  (
    'structure-document',
    '1.3',
    'intellex',
    'Structure Document',
    'Classify trimmed elements into chapters, sections, and body paragraphs; removes visual-page headings and generated descriptions using layout provenance.',
    array['text'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"element_count":{"type":"integer"}}}'::jsonb,
    '{"type":"object","properties":{"chapter_count":{"type":"integer"},"section_count":{"type":"integer"},"chapter_titles":{"type":"array"},"dropped_nontext":{"type":"object"}}}'::jsonb,
    '{"system":"Build a clean chapter/section Book model from provenance-aware elements.","user_template":"Structure source {{source_id}}."}'::jsonb
  ),
  (
    'validate-structure',
    '1.0',
    'intellex',
    'Validate Structure',
    'Cross-check the structured Book against the source PDF; raises on hard failure.',
    array['text'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"chapter_count":{"type":"integer"}}}'::jsonb,
    '{"type":"object","properties":{"valid":{"type":"boolean"},"warnings":{"type":"array"},"checked":{"type":"object"}}}'::jsonb,
    '{"system":"Validate structured book against source PDF text layer.","user_template":"Validate structure for source {{source_id}}."}'::jsonb
  ),
  (
    'source-research',
    '1.0',
    'intellex',
    'Source Research',
    'Extract title, issuing authority, version, publication date, and distribution line from early parsed pages with optional web gap-fill for title and authority.',
    array['text'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"parsed_text":{"type":"string"}}}'::jsonb,
    '{
      "type": "object",
      "required": ["document_type", "title"],
      "properties": {
        "document_type": {"type": "string"},
        "title": {"type": "string"},
        "identifier": {"type": "string"},
        "issuing_authority": {"type": "string"},
        "authors": {"type": "array"},
        "version": {"type": "string"},
        "publication_date_in_document": {"type": "string"},
        "publication_date_public": {"type": "string"},
        "source_url": {"type": "string"},
        "abstract": {"type": "string"},
        "distribution_line": {"type": "string"},
        "confidence": {"type": "object"},
        "provenance": {"type": "object"},
        "web_sources": {"type": "array"}
      }
    }'::jsonb,
    '{
      "system": "Extract bibliographic metadata from the early pages of a parsed document: title, issuing authority, version, publication date, and distribution line.",
      "user_template": "Metadata slice extraction for source {{source_id}}."
    }'::jsonb
  ),
  (
    'source-research',
    '2.0',
    'intellex',
    'Source Research',
    'Extract a source profile from early parsed pages: bibliographic metadata plus purpose, target audience, and scope.',
    array['text'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"filename":{"type":"string"},"mime_type":{"type":"string"},"page_count":{"type":"integer"}}}'::jsonb,
    '{
      "type": "object",
      "required": ["document_type", "title"],
      "properties": {
        "document_type": {"type": "string"},
        "title": {"type": "string"},
        "identifier": {"type": "string"},
        "issuing_authority": {"type": "string"},
        "authors": {"type": "array"},
        "version": {"type": "string"},
        "publication_date_in_document": {"type": "string"},
        "publication_date_public": {"type": "string"},
        "source_url": {"type": "string"},
        "abstract": {"type": "string"},
        "distribution_line": {"type": "string"},
        "purpose": {"type": "string"},
        "target_audience": {"type": "string"},
        "scope": {"type": "string"},
        "confidence": {"type": "object"},
        "provenance": {"type": "object"}
      }
    }'::jsonb,
    '{
      "system": "Extract a source profile from labeled early-page sections of a parsed PDF.",
      "user_template": "Source profile extraction for source {{source_id}}."
    }'::jsonb
  ),
  (
    'source-research',
    '2.1',
    'intellex',
    'Source Research',
    'Extract a source profile from early parsed pages (document-only); web verification is a separate stage.',
    array['text'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"filename":{"type":"string"},"mime_type":{"type":"string"},"page_count":{"type":"integer"}}}'::jsonb,
    '{
      "type": "object",
      "required": ["document_type", "title"],
      "properties": {
        "document_type": {"type": "string"},
        "title": {"type": "string"},
        "identifier": {"type": "string"},
        "issuing_authority": {"type": "string"},
        "authors": {"type": "array"},
        "version": {"type": "string"},
        "publication_date_in_document": {"type": "string"},
        "publication_date_public": {"type": "string"},
        "source_url": {"type": "string"},
        "abstract": {"type": "string"},
        "distribution_line": {"type": "string"},
        "purpose": {"type": "string"},
        "target_audience": {"type": "string"},
        "scope": {"type": "string"},
        "confidence": {"type": "object"},
        "provenance": {"type": "object"},
        "web_sources": {"type": "array"}
      }
    }'::jsonb,
    '{
      "system": "Extract a source profile from labeled early-page sections of a parsed PDF. Do not search the web; leave gap-fill to web-enrichment.",
      "user_template": "Source profile extraction for source {{source_id}}."
    }'::jsonb
  ),
  (
    'web-enrichment',
    '1.0',
    'intellex',
    'Web Enrichment',
    'Verify the extracted source profile against the public record via LLM web search; skipped when distribution marks the document non-public.',
    array['text'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"title":{"type":"string"},"identifier":{"type":"string"},"distribution_line":{"type":"string"}}}'::jsonb,
    '{
      "type": "object",
      "properties": {
        "status": {"type": "string"},
        "superseded_by": {"type": "string"},
        "canonical_url": {"type": "string"},
        "publication_date_public": {"type": "string"},
        "publisher_context": {"type": "string"},
        "public_abstract": {"type": "string"},
        "confirmations": {"type": "array"},
        "corrections": {"type": "object"},
        "related_documents": {"type": "array"},
        "web_sources": {"type": "array"},
        "confidence": {"type": "object"},
        "searched": {"type": "boolean"},
        "skip_reason": {"type": "string"}
      }
    }'::jsonb,
    '{
      "system": "Verify bibliographic facts against the public web. Cite every populated field in web_sources. Document-extracted values win on conflict.",
      "user_template": "Web-enrich source profile for source {{source_id}}."
    }'::jsonb
  ),
  (
    'prepare-document',
    '1.0',
    'intellex',
    'Prepare Document',
    'Strip non-narration content from parsed documents before chunking using GPT-4o-mini.',
    array['text'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"line_count":{"type":"integer"},"page_count":{"type":"integer"}}}'::jsonb,
    '{"type":"object","properties":{"excluded_line_ids":{"type":"array"},"excluded_pages":{"type":"array"},"kept_line_count":{"type":"integer"},"excluded_line_count":{"type":"integer"}}}'::jsonb,
    '{"system":"Identify parsed document content that should not be included in audio narration.","user_template":"Prepare source {{source_id}} for narration."}'::jsonb
  ),
  (
    'prepare-document',
    '2.0',
    'intellex',
    'Prepare Document',
    'Remove all non-learning content; keep only chapter/section headings and their body text.',
    array['text'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"line_count":{"type":"integer"},"page_count":{"type":"integer"}}}'::jsonb,
    '{"type":"object","properties":{"excluded_line_ids":{"type":"array"},"excluded_pages":{"type":"array"},"kept_line_count":{"type":"integer"},"excluded_line_count":{"type":"integer"},"pre_filter":{"type":"object"},"validation":{"type":"object"}}}'::jsonb,
    '{"system":"Extract learning content only: chapter/section headings and body text that teaches the subject. Remove TOC, glossaries, indexes, prefaces, page numbers, and all front/back matter.","user_template":"Prepare source {{source_id}} for learning content extraction."}'::jsonb
  ),
  (
    'deconstruct-document',
    '1.0',
    'intellex',
    'Deconstruct Document',
    'Identify essential terms and concepts required to understand a document and promote them to Wiki entries.',
    array['text'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"ndr_segment_ids":{"type":"array"}}}'::jsonb,
    '{
      "type": "object",
      "required": ["concepts"],
      "properties": {
        "concepts": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["term_label", "definition", "importance", "confidence"],
            "properties": {
              "term_label": {"type": "string"},
              "definition": {"type": "string"},
              "aliases": {"type": "array"},
              "prerequisite_labels": {"type": "array"},
              "pronunciation": {"type": "string"},
              "importance": {"type": "string"},
              "evidence_segment_ids": {"type": "array"},
              "confidence": {"type": "number"}
            }
          }
        }
      }
    }'::jsonb,
    '{
      "system": "Deconstruct the document into essential terms and concepts. Do not summarize or produce lesson narrative.",
      "user_template": "Extract concepts for source {{source_id}} from NDR segments."
    }'::jsonb
  ),
  (
    'deconstruct-document',
    '2.0',
    'intellex',
    'Deconstruct Document',
    'Segment prepared document into chapters/sections for downstream chapter-by-chapter processing.',
    array['text'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"segment_count":{"type":"integer"}}}'::jsonb,
    '{"type":"object","required":["chapters"],"properties":{"chapters":{"type":"array","items":{"type":"object","required":["sequence_index","title","level","segment_ids"],"properties":{"sequence_index":{"type":"integer"},"title":{"type":"string"},"level":{"type":"integer"},"segment_ids":{"type":"array"}}}}}}'::jsonb,
    '{"system":"Segment the document into chapters and sections. Assign every segment_id to exactly one chapter. Do not extract key terms.","user_template":"Segment source {{source_id}} into chapters from NDR segments."}'::jsonb
  ),
  (
    'extract-knowledge',
    '1.0',
    'intellex',
    'Extract Knowledge',
    'Extract terms, concepts, and insights from each chapter via isolated LLM calls.',
    array['text'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"chapter_count":{"type":"integer"},"segment_count":{"type":"integer"}}}'::jsonb,
    '{"type":"object","properties":{"chapters":{"type":"array"},"items":{"type":"array"},"item_counts":{"type":"object"}}}'::jsonb,
    '{"system":"Extract terms, concepts, and insights from one chapter at a time. Ground every item in chapter segment text.","user_template":"Extract knowledge for chapter {{chapter_title}} in source {{source_id}}."}'::jsonb
  ),
  (
    'extract-knowledge',
    '2.1',
    'intellex',
    'Extract Knowledge',
    'Derive Bloom-aligned learning objectives per chapter, then extract terms, concepts, and insights with evidence quotes and objective mapping.',
    array['text'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"chapter_count":{"type":"integer"},"segment_count":{"type":"integer"}}}'::jsonb,
    '{
      "type": "object",
      "properties": {
        "chapters": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "chapter_id": {"type": "string"},
              "chapter_title": {"type": "string"},
              "sequence_index": {"type": "integer"},
              "learning_objectives": {"type": "array"},
              "items": {"type": "array"}
            }
          }
        },
        "items": {"type": "array"},
        "learning_objectives": {"type": "array"},
        "item_counts": {"type": "object"}
      }
    }'::jsonb,
    '{
      "system": "Derive learning objectives for each chapter, then extract grounded terms, concepts, and insights with evidence quotes mapped to objectives.",
      "user_template": "Extract knowledge for chapter {{chapter_title}} in source {{source_id}}."
    }'::jsonb
  ),
  (
    'create-ebook',
    '1.0',
    'mathesys',
    'Create EBook',
    'Render the structured Book to an EPUB for manual ElevenReader upload.',
    array['text'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"chapter_count":{"type":"integer"}}}'::jsonb,
    '{"type":"object","properties":{"files":{"type":"array"},"chapter_titles":{"type":"array"}}}'::jsonb,
    '{"system":"Build one EPUB per source from the persisted structured Book.","user_template":"Create EPUB for source {{source_id}} with {{chapter_count}} chapters."}'::jsonb
  ),
  (
    'export-wiki-json',
    '1.0',
    'mathesys',
    'Export Wiki JSON',
    'Snapshot the curated canonical wiki entries for a source into a JSON artifact.',
    array['text'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"entry_count":{"type":"integer"}}}'::jsonb,
    '{
      "type": "object",
      "required": ["files", "entry_count"],
      "properties": {
        "files": {"type": "array"},
        "entry_count": {"type": "integer"},
        "entry_kind_counts": {"type": "object"}
      }
    }'::jsonb,
    '{}'::jsonb
  ),
  (
    'generate-narration',
    '1.0',
    'mathesys',
    'Generate Narration',
    'Synthesize per-chapter TTS narration with word-level timing. Chapters that exceed the provider character cap are split on paragraph boundaries. Stored as narration_segments rows (shared chapter audio_path) for the Reader''s read-while-listen mode.',
    array['text', 'audio'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"voice_id":{"type":"string"},"model_id":{"type":"string"}}}'::jsonb,
    '{"type":"object","properties":{"segments_narrated":{"type":"integer"},"segments_reused":{"type":"integer"},"segments_skipped":{"type":"integer"},"character_count":{"type":"integer"}}}'::jsonb,
    '{}'::jsonb
  ),
  (
    'elevenreader-ebook',
    '1.0',
    'mathesys',
    'ElevenReader EBook',
    'Generate a Wiki-aware, content-only EPUB EBook for easy import into ElevenReader.',
    array['text'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"wiki_entry_ids":{"type":"array"}}}'::jsonb,
    '{"type":"object","properties":{"manifest":{"type":"object"},"files":{"type":"array"}}}'::jsonb,
    '{"system":"Transform source text into clean, listenable EPUB prose using canonical wiki terminology.","user_template":"Generate ElevenReader EPUB for source {{source_id}}."}'::jsonb
  ),
  (
    'elevenreader-ebook',
    '2.0',
    'mathesys',
    'ElevenReader EBook',
    'Build one simple, audio-friendly EPUB from document chapters (titles + subsection headings + body text) for manual ElevenReader upload.',
    array['text'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"segment_count":{"type":"integer"},"chapter_count":{"type":"integer"}}}'::jsonb,
    '{"type":"object","properties":{"files":{"type":"array"},"chapter_count":{"type":"integer"},"chapter_titles":{"type":"array"}}}'::jsonb,
    '{"system":"Build one EPUB per source from persisted document_chapters. Each chapter becomes one spine item with an h1 title, h2 subsection headings, and paragraph body text. No LLM transformation.","user_template":"Generate ElevenReader EPUB for source {{source_id}} with {{chapter_count}} chapters."}'::jsonb
  ),
  (
    'speechify-audio',
    '1.0',
    'mathesys',
    'Speechify Audio',
    'Convert source text to clean SSML, then synthesize MP3 audio through the Speechify API.',
    array['text', 'audio'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"wiki_entry_ids":{"type":"array"}}}'::jsonb,
    '{"type":"object","properties":{"files":{"type":"array"},"manifest":{"type":"object"}}}'::jsonb,
    '{
      "system": "Transform source text into clean, listenable SSML, removing all non-content material, then synthesize audio with Speechify.",
      "user_template": "Generate Speechify audio for source {{source_id}}."
    }'::jsonb
  ),
  (
    'elevenlabs-audio',
    '1.0',
    'mathesys',
    'ElevenLabs Audio',
    'Convert source text to an ElevenLabs structured-text script, then synthesize MP3 audio through the ElevenLabs API.',
    array['text', 'audio'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"wiki_entry_ids":{"type":"array"}}}'::jsonb,
    '{"type":"object","properties":{"files":{"type":"array"},"manifest":{"type":"object"}}}'::jsonb,
    '{
      "system": "Transform source text into clean ElevenLabs structured narration text, removing all non-content material, then synthesize audio with ElevenLabs.",
      "user_template": "Generate ElevenLabs audio for source {{source_id}}."
    }'::jsonb
  ),
  (
    'generate-flashcards',
    '1.0',
    'qngen',
    'Generate Flashcards',
    'Generate memorization flashcards grounded in source segments and canonical wiki terminology.',
    array['text'],
    '{"type":"object"}'::jsonb,
    '{
      "type": "object",
      "required": ["flashcards"],
      "properties": {
        "flashcards": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["front", "back", "difficulty"],
            "properties": {
              "front": {"type": "string"},
              "back": {"type": "string"},
              "difficulty": {"type": "string"},
              "tags": {"type": "array"},
              "wiki_ids_cited": {"type": "array"},
              "segment_ids_used": {"type": "array"}
            }
          }
        }
      }
    }'::jsonb,
    '{
      "system": "Generate memorization flashcards from source material. Use canonical wiki terms exactly.",
      "user_template": "Create flashcards for source {{source_id}}."
    }'::jsonb
  ),
  (
    'generate-questions',
    '1.0',
    'qngen',
    'Generate Questions',
    'Generate understanding checks grounded in source segments and canonical wiki terminology.',
    array['text'],
    '{"type":"object"}'::jsonb,
    '{
      "type": "object",
      "required": ["questions"],
      "properties": {
        "questions": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["question", "question_type", "correct_answer", "difficulty"],
            "properties": {
              "question": {"type": "string"},
              "question_type": {"type": "string"},
              "options": {"type": "array"},
              "correct_answer": {"type": "string"},
              "explanation": {"type": "string"},
              "difficulty": {"type": "string"},
              "wiki_ids_cited": {"type": "array"},
              "segment_ids_used": {"type": "array"}
            }
          }
        }
      }
    }'::jsonb,
    '{
      "system": "Generate quiz questions that test understanding of source material.",
      "user_template": "Create quiz questions for source {{source_id}}."
    }'::jsonb
  ),
  (
    'generate-scenarios',
    '1.0',
    'qngen',
    'Generate Scenarios',
    'Generate application scenarios grounded in source doctrine and canonical wiki terminology.',
    array['text'],
    '{"type":"object"}'::jsonb,
    '{
      "type": "object",
      "required": ["scenarios"],
      "properties": {
        "scenarios": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["title", "prompt", "difficulty"],
            "properties": {
              "title": {"type": "string"},
              "prompt": {"type": "string"},
              "context": {"type": "string"},
              "evaluation_criteria": {"type": "array"},
              "difficulty": {"type": "string"},
              "wiki_ids_cited": {"type": "array"},
              "segment_ids_used": {"type": "array"}
            }
          }
        }
      }
    }'::jsonb,
    '{
      "system": "Generate realistic application scenarios from source material.",
      "user_template": "Create scenarios for source {{source_id}}."
    }'::jsonb
  ),
  (
    'generate-flashcards',
    '2.1',
    'qngen',
    'Generate Flashcards',
    'Generate memorization flashcards via skill-based draft/critique orchestration, grounded in wiki concepts, evidence segments, and learning objectives.',
    array['text'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"concept_count":{"type":"integer"},"batch_count":{"type":"integer"}}}'::jsonb,
    '{
      "type": "object",
      "required": ["items"],
      "properties": {
        "items": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["type", "subtype", "difficulty", "front", "back"],
            "properties": {
              "item_id": {"type": "string"},
              "type": {"type": "string"},
              "subtype": {"type": "string"},
              "difficulty": {"type": "string"},
              "wiki_ids_cited": {"type": "array"},
              "source_chunk_ids": {"type": "array"},
              "tags": {"type": "array"},
              "front": {"type": "string"},
              "back": {"type": "string"}
            }
          }
        },
        "flashcards": {"type": "array"}
      }
    }'::jsonb,
    '{
      "system": "Generate memorization flashcards from canonical wiki concepts using draft/critique skill orchestration.",
      "user_template": "Create flashcards for source {{source_id}}."
    }'::jsonb
  ),
  (
    'generate-questions',
    '2.1',
    'qngen',
    'Generate Questions',
    'Generate understanding checks via skill-based draft/critique orchestration, grounded in wiki concepts, evidence segments, and learning objectives.',
    array['text'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"concept_count":{"type":"integer"},"batch_count":{"type":"integer"}}}'::jsonb,
    '{
      "type": "object",
      "required": ["items"],
      "properties": {
        "items": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["type", "subtype", "difficulty", "question", "correct_answer"],
            "properties": {
              "item_id": {"type": "string"},
              "type": {"type": "string"},
              "subtype": {"type": "string"},
              "difficulty": {"type": "string"},
              "wiki_ids_cited": {"type": "array"},
              "source_chunk_ids": {"type": "array"},
              "question": {"type": "string"},
              "choices": {"type": "array"},
              "correct_answer": {"type": "string"},
              "explanation": {"type": "string"}
            }
          }
        },
        "questions": {"type": "array"}
      }
    }'::jsonb,
    '{
      "system": "Generate quiz questions that test understanding using draft/critique skill orchestration.",
      "user_template": "Create quiz questions for source {{source_id}}."
    }'::jsonb
  ),
  (
    'generate-scenarios',
    '2.1',
    'qngen',
    'Generate Scenarios',
    'Generate application scenarios via skill-based draft/critique orchestration, grounded in essential wiki concepts and evidence segments.',
    array['text'],
    '{"type":"object","properties":{"source_id":{"type":"string"},"concept_count":{"type":"integer"},"batch_count":{"type":"integer"}}}'::jsonb,
    '{
      "type": "object",
      "required": ["items"],
      "properties": {
        "items": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["type", "subtype", "difficulty", "situation", "task"],
            "properties": {
              "item_id": {"type": "string"},
              "type": {"type": "string"},
              "subtype": {"type": "string"},
              "difficulty": {"type": "string"},
              "wiki_ids_cited": {"type": "array"},
              "source_chunk_ids": {"type": "array"},
              "situation": {"type": "string"},
              "task": {"type": "string"},
              "expected_response_elements": {"type": "array"},
              "rubric": {"type": "object"}
            }
          }
        },
        "scenarios": {"type": "array"}
      }
    }'::jsonb,
    '{
      "system": "Generate realistic application scenarios using draft/critique skill orchestration.",
      "user_template": "Create scenarios for source {{source_id}}."
    }'::jsonb
  ),
  (
    'transcribe-wiki-notes',
    '1.0',
    'intellex',
    'Transcribe Wiki Notes',
    'Turn uploaded wiki note files into markdown (passthrough for text; LlamaParse for PDF, DOCX, and images). Skipped when notes were pasted.',
    array['text'],
    '{"type":"object","properties":{"production_run_id":{"type":"string"},"batch_id":{"type":"string"}}}'::jsonb,
    '{"type":"object","properties":{"skipped":{"type":"boolean"},"attachment_count":{"type":"integer"},"raw_notes_chars":{"type":"integer"}}}'::jsonb,
    '{"system":"Transcribe wiki note attachments into markdown.","user_template":"Transcribe notes for production run {{production_run_id}}."}'::jsonb
  ),
  (
    'structure-wiki-notes',
    '1.0',
    'intellex',
    'Structure Wiki Notes',
    'Format reader notes into canonical wiki entries and write them immediately (merge/conflict uses the new definition).',
    array['text'],
    '{"type":"object","properties":{"production_run_id":{"type":"string"},"batch_id":{"type":"string"}}}'::jsonb,
    '{"type":"object","properties":{"entry_count":{"type":"integer"},"inserted_ids":{"type":"array"},"updated_ids":{"type":"array"}}}'::jsonb,
    '{"system":"Structure reader notes into wiki entries without inventing facts.","user_template":"Structure notes for production run {{production_run_id}}."}'::jsonb
  )
on conflict (stage_id, version) do update
set
  module = excluded.module,
  name = excluded.name,
  description = excluded.description,
  modalities = excluded.modalities,
  input_schema = excluded.input_schema,
  output_schema = excluded.output_schema,
  prompts = excluded.prompts;

-- Retired stages kept for historical stage_runs FK compatibility.
update public.stages
set is_active = false
where stage_id in (
  'prepare-document',
  'deconstruct-document',
  'extract-knowledge',
  'elevenreader-ebook',
  'speechify-audio',
  'elevenlabs-audio'
);
