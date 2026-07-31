export const SHEEKO_LANGUAGES = Object.freeze([
  Object.freeze({ uiCode: "aa", iso6393: "aar", label: "QAFAR AF", name: "Afar", elevenLabs: false }),
  Object.freeze({ uiCode: "am", iso6393: "amh", label: "አማርኛ", name: "Amharic", elevenLabs: false }),
  Object.freeze({ uiCode: "om", iso6393: "orm", label: "AFAAN OROMOO", name: "Oromo", elevenLabs: false }),
  Object.freeze({ uiCode: "so", iso6393: "som", label: "AF-SOOMAALI", name: "Somali", elevenLabs: true }),
  Object.freeze({ uiCode: "sw", iso6393: "swa", label: "KISWAHILI", name: "Swahili", elevenLabs: true })
]);

export const EMPTY_LANGUAGE_VERSION = Object.freeze({
  script: "",
  character_assignments: [],
  athero_voice_id: "",
  narrator_voice_id: "",
  character_voices: {},
  pronunciation_notes: "",
  generated_audio_url: null,
  subtitle_url: null,
  translation_review_status: "pending",
  voice_review_status: "pending",
  final_approval_status: "pending",
  audio_assets: []
});

export function indexLanguageVersions(versions = []) {
  return Object.fromEntries(
    SHEEKO_LANGUAGES.map(language => [
      language.uiCode,
      { ...EMPTY_LANGUAGE_VERSION, language_code: language.uiCode, iso_639_3: language.iso6393 }
    ]).map(([code, fallback]) => [
      code,
      { ...fallback, ...(versions.find(version => version.language_code === code) || {}) }
    ])
  );
}

export function isMultilingualComplete(versions) {
  const indexed = Array.isArray(versions) ? indexLanguageVersions(versions) : versions;
  return SHEEKO_LANGUAGES.every(
    language => indexed?.[language.uiCode]?.final_approval_status === "approved"
  );
}

export function languageProgress(version) {
  if (version.final_approval_status === "approved") return "Complete";
  if (version.translation_review_status !== "approved") {
    return version.script?.trim() ? "Translation review pending" : "Translation pending";
  }
  if (!version.generated_audio_url) return "Script approved / Voice pending";
  if (version.voice_review_status !== "approved") return "Script approved / Voice generated";
  return "Final approval pending";
}

export function subtitleFilename(episodeSlug, language) {
  return `sheeko-xariiro_${episodeSlug}_${language}.vtt`;
}
