/**
 * Browser-native text-to-speech (SpeechSynthesis).
 * Zero server load — better for concurrency — and works offline.
 * Strips markdown the same way the backend's clean_for_tts does.
 */

let _voices: SpeechSynthesisVoice[] = [];

function loadVoices(): SpeechSynthesisVoice[] {
  if (typeof window === "undefined" || !window.speechSynthesis) return [];
  if (_voices.length) return _voices;
  _voices = window.speechSynthesis.getVoices();
  return _voices;
}

if (typeof window !== "undefined" && window.speechSynthesis) {
  window.speechSynthesis.onvoiceschanged = () => {
    _voices = window.speechSynthesis.getVoices();
  };
}

export function isTTSSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

function cleanForSpeech(text: string): string {
  let c = text;
  const da = c.match(/\*\*Direct Answer:\*\*\s*([\s\S]*?)(?:\*\*Step|$)/);
  if (da) c = da[1].trim();
  c = c.replace(/\*\*([^*]+)\*\*/g, "$1");
  c = c.replace(/#{1,3}\s*/g, "");
  c = c.replace(/\[Source[\s\S]*?\]/g, "");
  c = c.replace(/---[\s\S]*$/g, "");
  c = c.replace(/📚[\s\S]*$/g, "");
  c = c.replace(/^\s*\d+\.\s*/gm, ". ");
  c = c.replace(/[*_`~]/g, "");
  c = c.replace(/\s+/g, " ").trim();
  if (c.length > 700) c = c.slice(0, 700) + ".";
  return c;
}

export function speak(text: string, lang: string): void {
  if (!isTTSSupported()) return;
  window.speechSynthesis.cancel();
  const clean = cleanForSpeech(text);
  if (clean.length < 6) return;

  const utter = new SpeechSynthesisUtterance(clean);
  const want = lang === "hi" ? "hi" : "en";
  const voices = loadVoices();
  const match =
    voices.find((v) => v.lang?.toLowerCase().startsWith(want === "hi" ? "hi" : "en-in")) ||
    voices.find((v) => v.lang?.toLowerCase().startsWith(want)) ||
    voices.find((v) => v.lang?.toLowerCase().startsWith("en"));
  if (match) utter.voice = match;
  utter.lang = match?.lang || (want === "hi" ? "hi-IN" : "en-IN");
  utter.rate = 0.95;
  utter.pitch = 1;
  window.speechSynthesis.speak(utter);
}

export function stopSpeaking(): void {
  if (isTTSSupported()) window.speechSynthesis.cancel();
}
