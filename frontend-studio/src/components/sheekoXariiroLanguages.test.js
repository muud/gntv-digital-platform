import assert from "node:assert/strict";
import test from "node:test";

import {
  SHEEKO_LANGUAGES,
  indexLanguageVersions,
  isMultilingualComplete,
  languageProgress,
  subtitleFilename
} from "./sheekoXariiroLanguages.js";

test("keeps all five UI and ISO-639-3 language codes permanent", () => {
  assert.deepEqual(SHEEKO_LANGUAGES.map(item => item.uiCode), ["aa", "am", "om", "so", "sw"]);
  assert.deepEqual(SHEEKO_LANGUAGES.map(item => item.iso6393), ["aar", "amh", "orm", "som", "swa"]);
  assert.deepEqual(SHEEKO_LANGUAGES.filter(item => item.elevenLabs).map(item => item.uiCode), ["so", "sw"]);
});

test("indexes scripts and audio independently when switching languages", () => {
  const versions = indexLanguageVersions([
    { language_code: "so", script: "Sheekada Soomaaliga", generated_audio_url: "/so.mp3" },
    { language_code: "sw", script: "Hadithi ya Kiswahili", generated_audio_url: "/sw.mp3" }
  ]);
  assert.equal(versions.so.script, "Sheekada Soomaaliga");
  assert.equal(versions.sw.script, "Hadithi ya Kiswahili");
  assert.equal(versions.aa.script, "");
  assert.notEqual(versions.so.generated_audio_url, versions.sw.generated_audio_url);
});

test("requires final approval for every language before multilingual completion", () => {
  const versions = indexLanguageVersions();
  for (const language of SHEEKO_LANGUAGES) versions[language.uiCode].final_approval_status = "approved";
  assert.equal(isMultilingualComplete(versions), true);
  versions.om.final_approval_status = "in_review";
  assert.equal(isMultilingualComplete(versions), false);
  assert.equal(languageProgress(versions.om), "Translation pending");
});

test("exports a distinct subtitle filename per language", () => {
  assert.equal(subtitleFilename("diin-iyo-bakayle", "om"), "sheeko-xariiro_diin-iyo-bakayle_om.vtt");
  assert.notEqual(subtitleFilename("diin-iyo-bakayle", "so"), subtitleFilename("diin-iyo-bakayle", "sw"));
});
