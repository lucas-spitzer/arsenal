-- Existing-database patch: allow WAV narration clips in the sources bucket.
-- Cartesia and Gemini wrap PCM as audio/wav; Speechify/ElevenLabs stay audio/mpeg.
-- Fresh installs already include this in 04-storage-and-rls.sql.

update storage.buckets
set allowed_mime_types = array[
  'application/pdf',
  'text/markdown',
  'application/epub+zip',
  'application/json',
  'audio/mpeg',
  'audio/wav'
]
where id = 'sources';
