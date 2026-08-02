# ATANOR Voice Runtime Availability

Status: optional runtime checks only.

Voice remains an additive channel. Text input stays supported even if Nemotron
ASR or Fish TTS runtimes are unavailable. The availability checker only inspects
local Python module presence; it does not download models, open microphones,
synthesize audio, persist transcripts, write Local Brain, write Cloud Brain, or
replace the chat interface.
