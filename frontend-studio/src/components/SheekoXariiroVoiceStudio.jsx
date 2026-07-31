import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { store } from "../../../shared/src/state.js";
import {
  EMPTY_LANGUAGE_VERSION,
  SHEEKO_LANGUAGES,
  indexLanguageVersions,
  isMultilingualComplete,
  languageProgress
} from "./sheekoXariiroLanguages.js";

const apiBase = import.meta.env.VITE_API_URL || "http://localhost:8000";
const reviewOptions = ["pending", "in_review", "changes_requested", "approved"];

function getToken() {
  return localStorage.getItem("gntv_auth_token") || sessionStorage.getItem("gntv_studio_token");
}

async function request(path, options = {}) {
  const token = getToken();
  if (!token) throw new Error("Producer authentication is required.");
  const isForm = options.body instanceof FormData;
  const response = await fetch(`${apiBase}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(isForm ? {} : { "Content-Type": "application/json" }),
      ...(options.headers || {})
    }
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body?.detail?.message || `Voice Studio API returned ${response.status}`);
  }
  return response;
}

function Badge({ children, good = false }) {
  return <span className={`sx-badge ${good ? "good" : ""}`}>{children}</span>;
}

function VoiceStudio() {
  const [episode, setEpisode] = useState(null);
  const [episodeTitle, setEpisodeTitle] = useState("");
  const [originalScript, setOriginalScript] = useState("");
  const [activeLanguage, setActiveLanguage] = useState("aa");
  const [versions, setVersions] = useState(indexLanguageVersions());
  const [voices, setVoices] = useState([]);
  const [presets, setPresets] = useState([]);
  const [adminPresetName, setAdminPresetName] = useState("ATHERO");
  const [adminVoiceId, setAdminVoiceId] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [previewUrl, setPreviewUrl] = useState("");
  const [characterName, setCharacterName] = useState("ATHERO");
  const [sceneNumber, setSceneNumber] = useState(1);
  const [otherVoicesText, setOtherVoicesText] = useState("{}");
  const user = store.getState("user") || {};
  const language = SHEEKO_LANGUAGES.find(item => item.uiCode === activeLanguage);
  const version = versions[activeLanguage] || { ...EMPTY_LANGUAGE_VERSION };
  const complete = useMemo(() => isMultilingualComplete(versions), [versions]);
  const voiceOptions = useMemo(() => {
    if (presets.length) {
      return presets.map(preset => ({
        voice_id: preset.voice_id,
        name: `${preset.preset_name} · ${preset.character_name}`
      }));
    }
    return user.role === "admin" ? voices : [];
  }, [presets, voices, user.role]);

  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  useEffect(() => {
    if (!language?.elevenLabs || !episode) {
      setVoices([]);
      setPresets([]);
      return;
    }
    Promise.all([
      request(`/api/v1/sheeko-xariiro/voice-presets?language=${activeLanguage}`)
        .then(response => response.json()),
      user.role === "admin"
        ? request(`/api/v1/editorial/tts/voices?language=${activeLanguage}`)
          .then(response => response.json())
        : Promise.resolve({ voices: [] })
    ]).then(([approvedPresets, providerVoices]) => {
      setPresets(approvedPresets || []);
      setVoices(providerVoices.voices || []);
    }).catch(err => setError(err.message));
  }, [activeLanguage, episode?.id]);

  const clearMessages = () => {
    setError("");
    setNotice("");
  };

  const updateLocal = (field, value) => {
    setVersions(current => ({
      ...current,
      [activeLanguage]: { ...current[activeLanguage], [field]: value }
    }));
  };

  const createEpisode = async event => {
    event.preventDefault();
    clearMessages();
    setBusy("create");
    try {
      const response = await request("/api/v1/sheeko-xariiro/episodes", {
        method: "POST",
        body: JSON.stringify({ episode_title: episodeTitle, original_script: originalScript })
      });
      const created = await response.json();
      setEpisode(created);
      setVersions(indexLanguageVersions(created.languages));
      setNotice("Episode created with five independent language workspaces.");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  };

  const saveLanguage = async () => {
    clearMessages();
    setBusy("save");
    let characterVoices;
    try {
      characterVoices = JSON.parse(otherVoicesText || "{}");
    } catch {
      setError("Other character voices must be valid JSON, for example {\"BAKAYLE\":\"voice-id\"}.");
      setBusy("");
      return;
    }
    try {
      const response = await request(
        `/api/v1/sheeko-xariiro/episodes/${episode.id}/languages/${activeLanguage}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            script: version.script,
            character_assignments: version.character_assignments,
            athero_voice_id: version.athero_voice_id || null,
            narrator_voice_id: version.narrator_voice_id || null,
            character_voices: characterVoices,
            pronunciation_notes: version.pronunciation_notes,
            translation_review_status: version.translation_review_status,
            voice_review_status: version.voice_review_status,
            final_approval_status: version.final_approval_status
          })
        }
      );
      const saved = await response.json();
      setVersions(current => ({ ...current, [activeLanguage]: saved }));
      setNotice(`${language.name} production version saved.`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  };

  const voiceId = version.athero_voice_id || version.narrator_voice_id;

  const saveAdminPreset = async () => {
    clearMessages();
    if (!adminVoiceId) return setError("Choose an ElevenLabs voice to approve.");
    setBusy("preset");
    try {
      const response = await request("/api/v1/sheeko-xariiro/voice-presets", {
        method: "PUT",
        body: JSON.stringify({
          preset_name: adminPresetName,
          character_name: adminPresetName,
          language_code: activeLanguage,
          provider: "elevenlabs",
          voice_id: adminVoiceId,
          model_id: "eleven_v3",
          settings: {},
          active: true
        })
      });
      const preset = await response.json();
      setPresets(current => [...current.filter(item => item.preset_name !== preset.preset_name), preset]);
      setNotice(`${preset.preset_name} is now an approved ${language.name} voice preset.`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  };

  const preview = async () => {
    clearMessages();
    if (!voiceId) return setError("Select an approved Athero or narrator voice first.");
    setBusy("preview");
    try {
      const response = await request(
        `/api/v1/sheeko-xariiro/episodes/${episode.id}/languages/${activeLanguage}/preview`,
        {
          method: "POST",
          body: JSON.stringify({
            text: version.script.slice(0, 500),
            voice_id: voiceId,
            character_name: characterName,
            scene_number: Number(sceneNumber),
            idempotency_key: `preview-${crypto.randomUUID()}`
          })
        }
      );
      const blobUrl = URL.createObjectURL(await response.blob());
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      setPreviewUrl(blobUrl);
      setNotice("Preview ready. No full episode generation was triggered.");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  };

  const generate = async () => {
    clearMessages();
    if (!voiceId) return setError("Select an approved voice before generation.");
    setBusy("generate");
    try {
      const response = await request(
        `/api/v1/sheeko-xariiro/episodes/${episode.id}/languages/${activeLanguage}/generate`,
        {
          method: "POST",
          body: JSON.stringify({
            text: version.script,
            voice_id: voiceId,
            character_name: characterName,
            scene_number: Number(sceneNumber),
            idempotency_key: `generate-${crypto.randomUUID()}`
          })
        }
      );
      const asset = await response.json();
      updateLocal("generated_audio_url", asset.media_url);
      setVersions(current => ({
        ...current,
        [activeLanguage]: {
          ...current[activeLanguage],
          generated_audio_url: asset.media_url,
          audio_assets: [...(current[activeLanguage].audio_assets || []), asset]
        }
      }));
      setNotice(`Generated ${asset.filename}. Review it before approval.`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  };

  const uploadAudio = async event => {
    const file = event.target.files?.[0];
    if (!file) return;
    clearMessages();
    setBusy("upload");
    const form = new FormData();
    form.append("audio", file);
    try {
      const response = await request(
        `/api/v1/sheeko-xariiro/episodes/${episode.id}/languages/${activeLanguage}/audio-upload?character_name=${encodeURIComponent(characterName)}&scene_number=${Number(sceneNumber)}`,
        { method: "POST", body: form }
      );
      const asset = await response.json();
      setVersions(current => ({
        ...current,
        [activeLanguage]: {
          ...current[activeLanguage],
          generated_audio_url: asset.media_url,
          audio_assets: [...(current[activeLanguage].audio_assets || []), asset]
        }
      }));
      setNotice(`Approved recording uploaded as ${asset.filename}.`);
    } catch (err) {
      setError(err.message);
    } finally {
      event.target.value = "";
      setBusy("");
    }
  };

  const downloadProtected = async (url, fallbackName) => {
    clearMessages();
    try {
      const response = await request(url);
      const blobUrl = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = blobUrl;
      anchor.download = fallbackName;
      anchor.click();
      URL.revokeObjectURL(blobUrl);
    } catch (err) {
      setError(err.message);
    }
  };

  if (!episode) {
    return (
      <div className="sx-shell">
        <header className="sx-hero">
          <div><span className="sx-kicker">GNTV DIGITAL KIDS · AUTHORISED PRODUCERS</span>
            <h1>Sheeko Xariiro Voice Studio</h1>
            <p>Build one story in five independently reviewed production languages.</p>
          </div>
          <Badge>ATHERO IDENTITY LOCKED</Badge>
        </header>
        <form className="sx-create" onSubmit={createEpisode}>
          <label>Episode title<input required maxLength="240" value={episodeTitle} onChange={e => setEpisodeTitle(e.target.value)} placeholder="Diin iyo Bakayle" /></label>
          <label>Original script<textarea rows="10" maxLength="50000" value={originalScript} onChange={e => setOriginalScript(e.target.value)} placeholder="Paste the source script exactly as approved. It will not be translated automatically." /></label>
          <button className="sx-primary" disabled={busy === "create"}>{busy ? "Creating…" : "Create five-language episode"}</button>
          {error && <div className="sx-alert error">{error}</div>}
        </form>
      </div>
    );
  }

  return (
    <div className="sx-shell">
      <header className="sx-hero compact">
        <div><span className="sx-kicker">SHEEKO XARIIRO · {episode.slug}</span>
          <h1>{episode.episode_title}</h1>
          <p>Athero’s approved face, clothing, proportions, personality and programme branding stay identical in every language.</p>
        </div>
        <Badge good={complete}>{complete ? "MULTILINGUAL COMPLETE" : "5-LANGUAGE PRODUCTION"}</Badge>
      </header>

      <section className="sx-progress">
        {SHEEKO_LANGUAGES.map(item => (
          <button key={item.uiCode} onClick={() => setActiveLanguage(item.uiCode)} className={activeLanguage === item.uiCode ? "active" : ""}>
            <strong>{item.name}</strong><span>{languageProgress(versions[item.uiCode])}</span>
          </button>
        ))}
      </section>

      <nav className="sx-tabs" aria-label="Production languages">
        {SHEEKO_LANGUAGES.map(item => (
          <button key={item.uiCode} aria-selected={activeLanguage === item.uiCode} onClick={() => {
            setActiveLanguage(item.uiCode);
            setOtherVoicesText(JSON.stringify(versions[item.uiCode]?.character_voices || {}, null, 2));
            clearMessages();
          }}>{item.label}<small>{item.uiCode} · {item.iso6393}</small></button>
        ))}
      </nav>

      {!language.elevenLabs && (
        <div className="sx-alert info">
          AI voice provider is not yet configured for this language. Upload an approved WAV or MP3 recording below; production is not blocked.
        </div>
      )}
      {notice && <div className="sx-alert success">{notice}</div>}
      {error && <div className="sx-alert error">{error}</div>}

      <div className="sx-grid">
        <section className="sx-card sx-script">
          <h2>{language.label} Script Editor</h2>
          <label>Language script<textarea rows="17" value={version.script} onChange={e => updateLocal("script", e.target.value)} placeholder={`Enter the reviewed ${language.name} script. No automatic translation.`} /></label>
          <div className="sx-meta"><span>{version.script.length.toLocaleString()} characters</span>{version.script.split(/[.!?።]\s*/).some(line => line.length > 300) && <span className="warn">Long sentence detected</span>}</div>
          <label>Pronunciation notes<textarea rows="4" value={version.pronunciation_notes} onChange={e => updateLocal("pronunciation_notes", e.target.value)} placeholder="Names, traditional words, pauses and native-editor guidance" /></label>
        </section>

        <section className="sx-card">
          <h2>Character & Voice Assignment</h2>
          <div className="sx-two">
            <label>Scene<input type="number" min="1" value={sceneNumber} onChange={e => setSceneNumber(e.target.value)} /></label>
            <label>Character<select value={characterName} onChange={e => setCharacterName(e.target.value)}>
              <option>SHEEKO-WADAHA</option><option>ATHERO</option><option>MACALLINKA</option><option>XAYAWAANKA</option><option>CUSTOM CHARACTER</option>
            </select></label>
          </div>
          <label>Athero voice<select value={version.athero_voice_id || ""} onChange={e => updateLocal("athero_voice_id", e.target.value)}>
            <option value="">Select approved youthful adult voice</option>
            {voiceOptions.map(voice => <option key={voice.voice_id} value={voice.voice_id}>{voice.name}</option>)}
          </select></label>
          <label>Narrator voice<select value={version.narrator_voice_id || ""} onChange={e => updateLocal("narrator_voice_id", e.target.value)}>
            <option value="">Select approved narrator voice</option>
            {voiceOptions.map(voice => <option key={voice.voice_id} value={voice.voice_id}>{voice.name}</option>)}
          </select></label>
          <label>Other character voices (JSON)<textarea rows="4" value={otherVoicesText} onChange={e => setOtherVoicesText(e.target.value)} /></label>
          <div className="sx-safety">Athero uses an approved adult animation voice. Never clone or imitate a real child.</div>
          {user.role === "admin" && language.elevenLabs && <div className="sx-admin"><strong>Admin-only approved voice configuration</strong>
            <label>Preset<select value={adminPresetName} onChange={e => setAdminPresetName(e.target.value)}><option>ATHERO</option><option>SHEEKO-WADAHA</option><option>MACALLINKA</option><option>XAYAWAANKA</option></select></label>
            <label>Provider voice<select value={adminVoiceId} onChange={e => setAdminVoiceId(e.target.value)}><option value="">Select ElevenLabs voice</option>{voices.map(voice => <option key={voice.voice_id} value={voice.voice_id}>{voice.name}</option>)}</select></label>
            <button onClick={saveAdminPreset} disabled={busy === "preset"}>Approve preset · eleven_v3</button>
          </div>}
          {user.role === "admin" && !language.elevenLabs && <div className="sx-admin"><strong>Provider adapter required</strong><span>This language cannot be labeled ElevenLabs-supported. Configure a licensed backend adapter first; approved WAV/MP3 upload remains available.</span></div>}
        </section>

        <section className="sx-card">
          <h2>Preview & Production Audio</h2>
          <div className="sx-actions">
            <button onClick={preview} disabled={!language.elevenLabs || busy}>Preview</button>
            <button className="sx-primary" onClick={generate} disabled={!language.elevenLabs || busy}>{version.generated_audio_url ? "Regenerate" : "Generate"}</button>
            <label className="sx-upload">Upload WAV / MP3<input hidden type="file" accept=".wav,.mp3,audio/wav,audio/mpeg" onChange={uploadAudio} /></label>
          </div>
          {previewUrl && <audio controls src={previewUrl} />}
          <div className="sx-assets">
            {(version.audio_assets || []).map(asset => (
              <div key={asset.id}><span><strong>{asset.character_name}</strong><small>{asset.source} · v{asset.version} · {asset.filename}</small></span>
                <button onClick={() => downloadProtected(asset.media_url, asset.filename)}>Download</button>
              </div>
            ))}
            {!version.audio_assets?.length && <p>No audio generated or uploaded for {language.name}.</p>}
          </div>
          <button onClick={() => downloadProtected(`/api/v1/sheeko-xariiro/episodes/${episode.id}/languages/${activeLanguage}/subtitles`, `sheeko-xariiro_${episode.slug}_${activeLanguage}.vtt`)}>Export {language.name} subtitles</button>
        </section>

        <section className="sx-card">
          <h2>Native Review & Approval</h2>
          <label>Translation review<select value={version.translation_review_status} onChange={e => updateLocal("translation_review_status", e.target.value)}>{reviewOptions.map(value => <option key={value}>{value}</option>)}</select></label>
          <label>Voice review<select value={version.voice_review_status} onChange={e => updateLocal("voice_review_status", e.target.value)}>{reviewOptions.map(value => <option key={value}>{value}</option>)}</select></label>
          <label>Final approval<select value={version.final_approval_status} onChange={e => updateLocal("final_approval_status", e.target.value)}>{reviewOptions.map(value => <option key={value}>{value}</option>)}</select></label>
          <p className="sx-lock">Once translation is approved, changing its script is blocked until an editor returns it to review.</p>
          <button className="sx-primary full" onClick={saveLanguage} disabled={busy === "save"}>{busy === "save" ? "Saving…" : `Save ${language.name} version`}</button>
        </section>
      </div>
    </div>
  );
}

const styles = `
  .sx-shell{color:#f8fafc;max-width:1500px;margin:auto}.sx-hero{display:flex;justify-content:space-between;gap:24px;align-items:flex-start;padding:28px;border:1px solid rgba(255,255,255,.09);border-radius:18px;background:radial-gradient(circle at 85% 10%,rgba(255,42,75,.22),transparent 28%),linear-gradient(135deg,#151020,#090b13)}.sx-hero h1{font-size:30px;margin:5px 0 8px;letter-spacing:-1px}.sx-hero p{color:#a7b0c0;margin:0;max-width:780px;line-height:1.5}.sx-kicker{font:800 10px var(--font-mono);letter-spacing:1.5px;color:#ff758c}.sx-badge{white-space:nowrap;border:1px solid #ff506c;color:#ff8ca0;padding:8px 12px;border-radius:999px;font-size:10px;font-weight:900}.sx-badge.good{border-color:#22c55e;color:#65e692}.sx-create{max-width:850px;margin:28px auto;background:#10131c;border:1px solid rgba(255,255,255,.08);padding:28px;border-radius:16px}.sx-shell label{display:flex;flex-direction:column;gap:7px;font-size:11px;text-transform:uppercase;font-weight:800;color:#9aa4b5;margin-bottom:16px}.sx-shell input,.sx-shell textarea,.sx-shell select{box-sizing:border-box;width:100%;background:#090b12;border:1px solid rgba(255,255,255,.12);border-radius:9px;color:white;padding:11px 12px;font:500 13px var(--font-sans);resize:vertical}.sx-shell input:focus,.sx-shell textarea:focus,.sx-shell select:focus{outline:2px solid rgba(255,42,75,.5);border-color:#ff2a4b}.sx-shell button,.sx-upload{border:1px solid rgba(255,255,255,.13);background:#191d28;color:#fff;border-radius:8px;padding:10px 14px;font-weight:800;font-size:11px;cursor:pointer;text-align:center}.sx-shell button:disabled{opacity:.38;cursor:not-allowed}.sx-primary{background:#e91f45!important;border-color:#ff4666!important}.sx-progress{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:14px 0}.sx-progress button{display:flex;flex-direction:column;text-align:left;gap:4px}.sx-progress button.active{border-color:#ff4967;background:#2b1420}.sx-progress span{font-size:9px;color:#98a2b3}.sx-tabs{display:grid;grid-template-columns:repeat(5,1fr);background:#0d1018;border:1px solid rgba(255,255,255,.08);border-radius:12px 12px 0 0;overflow:hidden}.sx-tabs button{border-radius:0;border-width:0 1px 0 0;padding:14px 8px}.sx-tabs button[aria-selected=true]{background:#e91f45}.sx-tabs small{display:block;font:500 9px var(--font-mono);opacity:.65;margin-top:4px}.sx-alert{padding:12px 15px;margin:12px 0;border-radius:8px;font-size:12px}.sx-alert.info{background:#15263c;color:#a9d5ff;border:1px solid #214b72}.sx-alert.success{background:#102a20;color:#8cf3b7;border:1px solid #1f6545}.sx-alert.error{background:#35151b;color:#ffabb9;border:1px solid #7b2535}.sx-grid{display:grid;grid-template-columns:1.25fr .75fr;gap:14px;margin-top:14px}.sx-card{background:#10131c;border:1px solid rgba(255,255,255,.08);padding:20px;border-radius:13px}.sx-card h2{font-size:13px;color:#ff6982;text-transform:uppercase;letter-spacing:.5px;margin:0 0 18px}.sx-script{grid-row:span 2}.sx-two{display:grid;grid-template-columns:120px 1fr;gap:12px}.sx-meta{display:flex;justify-content:space-between;color:#7f8998;font-size:10px;margin:-10px 0 15px}.sx-meta .warn{color:#ffb14a}.sx-safety,.sx-lock,.sx-admin{font-size:10px;line-height:1.5;color:#aab3c2;padding:10px;background:#171a24;border-radius:8px}.sx-admin{display:flex;flex-direction:column;margin-top:10px;border-left:3px solid #ff2a4b}.sx-actions{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}.sx-upload{margin:0!important;text-transform:none!important;color:white!important}.sx-card audio{width:100%;margin:8px 0}.sx-assets{display:flex;flex-direction:column;gap:7px;margin:10px 0 16px}.sx-assets>div{display:flex;justify-content:space-between;align-items:center;background:#090b12;padding:9px;border-radius:8px}.sx-assets span{display:flex;flex-direction:column;min-width:0}.sx-assets small{color:#8590a0;white-space:nowrap;text-overflow:ellipsis;overflow:hidden;max-width:450px}.sx-assets p{font-size:11px;color:#7e8795}.full{width:100%}@media(max-width:1000px){.sx-progress,.sx-tabs{grid-template-columns:1fr}.sx-grid{grid-template-columns:1fr}.sx-script{grid-row:auto}.sx-hero{flex-direction:column}}`;

export function initSheekoXariiroVoiceStudio(container) {
  const style = document.createElement("style");
  style.textContent = styles;
  container.appendChild(style);
  const mount = document.createElement("div");
  container.appendChild(mount);
  const root = createRoot(mount);
  root.render(<VoiceStudio />);
  return () => {
    root.unmount();
    style.remove();
  };
}
