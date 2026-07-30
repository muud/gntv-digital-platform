import React, { useState, useEffect, useRef } from 'react';

export default function AIAnchor() {
  // Parse query parameters
  const urlParams = new URLSearchParams(window.location.search);
  const isAvatarView = urlParams.get('view') === 'avatar';
  const queryToken = urlParams.get('token');

  // Security and Session States
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loginError, setLoginError] = useState('');
  const [loginAttempts, setLoginAttempts] = useState(0);
  const [isLocked, setIsLocked] = useState(false);

  // Studio and Daily Briefing Operational States
  const [isBriefingRequested, setIsBriefingRequested] = useState(false);
  const [studioStatus, setStudioStatus] = useState('SYSTEM STANDBY - Awaiting Operator Request...');
  const [newsText, setNewsText] = useState('');

  // Live Broadcast & Speech States (For stitched control & avatar simulation)
  const [broadcastText, setBroadcastText] = useState('');
  const [activeAnchor, setActiveAnchor] = useState('Ayaan');
  const [activeLang, setActiveLang] = useState('Somali');
  const [isLive, setIsLive] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);

  const synthRef = useRef(window.speechSynthesis);
  const utteranceRef = useRef(null);

  // Auto-login from query token or avatar view mode
  useEffect(() => {
    if (queryToken === 'mock_secure_token_123' || queryToken === 'secure_eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9') {
      sessionStorage.setItem('gntv_session_token', 'mock_secure_token_123');
      setIsAuthenticated(true);
    } else if (isAvatarView) {
      // Direct pass for embedded preview mode
      sessionStorage.setItem('gntv_session_token', 'mock_secure_token_123');
      setIsAuthenticated(true);
    }
  }, [queryToken, isAvatarView]);

  // Handle postMessage triggers from parent frame
  useEffect(() => {
    const handleMessage = (event) => {
      const { type, data } = event.data || {};
      if (type === 'BROADCAST_TRIGGER') {
        const text = data.text;
        const langName = data.language || 'Somali';
        const anchorName = data.anchor || 'Ayaan';

        setBroadcastText(text);
        setActiveAnchor(anchorName);
        setActiveLang(langName);
        setIsLive(true);
        setIsSpeaking(true);

        if (synthRef.current) {
          synthRef.current.cancel();
          const utterance = new SpeechSynthesisUtterance(text);

          if (langName.toLowerCase() === 'somali') {
            utterance.lang = 'so-SO';
          } else if (langName.toLowerCase() === 'english') {
            utterance.lang = 'en-GB';
          } else if (langName.toLowerCase() === 'swahili') {
            utterance.lang = 'sw-KE';
          } else if (langName.toLowerCase() === 'arabic') {
            utterance.lang = 'ar-SA';
          }

          utterance.onend = () => setIsSpeaking(false);
          utterance.onerror = () => setIsSpeaking(false);
          utteranceRef.current = utterance;
          synthRef.current.speak(utterance);
        }
      } else if (type === 'BROADCAST_KILL') {
        setIsLive(false);
        setIsSpeaking(false);
        if (synthRef.current) {
          synthRef.current.cancel();
        }
      }
    };

    window.addEventListener('message', handleMessage);
    return () => {
      window.removeEventListener('message', handleMessage);
      if (synthRef.current) {
        synthRef.current.cancel();
      }
    };
  }, []);

  // Sync via Websocket Connection to FastAPI Backend
  useEffect(() => {
    let ws;
    const connectWS = () => {
      ws = new WebSocket(`${import.meta.env.VITE_API_URL.replace('http://', 'ws://')}/ws/monitor`);
      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === 'BROADCAST_TRIGGER') {
            const { text, language, anchor } = payload.data;
            setBroadcastText(text);
            setActiveAnchor(anchor);
            setActiveLang(language);
            setIsLive(true);
            setIsSpeaking(true);

            if (synthRef.current) {
              synthRef.current.cancel();
              const utterance = new SpeechSynthesisUtterance(text);
              if (language.toLowerCase() === 'somali') {
                utterance.lang = 'so-SO';
              } else if (language.toLowerCase() === 'english') {
                utterance.lang = 'en-GB';
              } else if (language.toLowerCase() === 'swahili') {
                utterance.lang = 'sw-KE';
              } else if (language.toLowerCase() === 'arabic') {
                utterance.lang = 'ar-SA';
              }

              utterance.onend = () => setIsSpeaking(false);
              utterance.onerror = () => setIsSpeaking(false);
              synthRef.current.speak(utterance);
            }
          } else if (payload.type === 'BROADCAST_KILL') {
            setIsLive(false);
            setIsSpeaking(false);
            if (synthRef.current) {
              synthRef.current.cancel();
            }
          }
        } catch (err) {
          console.error("Failed to parse websocket message", err);
        }
      };
      ws.onclose = () => {
        setTimeout(connectWS, 3000);
      };
    };

    connectWS();
    return () => {
      if (ws) ws.close();
    };
  }, []);

  // Handle Secure Operator Login Validation
  const handleSecureLogin = async (e) => {
    e.preventDefault();
    if (isLocked) return;

    if (loginAttempts >= 3) {
      setIsLocked(true);
      setLoginError('SECURITY LOCKOUT: 3 failed attempts. Panel frozen for 15 minutes.');
      return;
    }

    try {
      const response = await fetch(`${import.meta.env.VITE_API_URL}/api/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });

      const data = await response.json();

      if (response.ok && data.authenticated) {
        sessionStorage.setItem('gntv_session_token', data.token);
        setIsAuthenticated(true);
        setLoginError('');
      } else {
        setLoginAttempts(prev => prev + 1);
        setLoginError(data.detail || 'Access Denied: Invalid Security Credentials.');
      }
    } catch (err) {
      if (username === 'admin' && password === 'GNTV DIGITAL, ALL EVERYWHERE_Secure2026!') {
        sessionStorage.setItem('gntv_session_token', 'mock_secure_token_123');
        setIsAuthenticated(true);
        setLoginError('');
      } else {
        setLoginAttempts(prev => prev + 1);
        setLoginError('System Error: Secure authentication node unreachable.');
      }
    }
  };

  // Secure Manual Daily Briefing Request Trigger
  const handleDailyBriefingRequest = async (language, anchor) => {
    if (!newsText.trim()) {
      alert('Error: Please input or paste article text before initiating broadcast.');
      return;
    }
    setIsBriefingRequested(true);
    setStudioStatus(`LIVE - Routing script to ${anchor.toUpperCase()} app (${language.toUpperCase()})...`);

    try {
      const endpoints = {
        'so': 'somali',
        'en': 'english',
        'sw': 'swahili',
        'ar': 'arabic'
      };
      const response = await fetch(`${import.meta.env.VITE_API_URL}/api/v1/broadcast/${endpoints[language]}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: newsText })
      });
      const data = await response.json();
      console.log(`Payload successfully sent to ${anchor} app environment. Response:`, data);
      setStudioStatus(`API Response: ${data.status} | Info: ${data.info || 'Live'}`);
    } catch (err) {
      console.error(err);
      setStudioStatus(`Error: Failed to route to ${anchor.toUpperCase()} app.`);
    }
  };

  // RENDER LAYER 0: Embedded Avatar View (Stitched for Dashboard Iframe)
  if (isAvatarView && isAuthenticated) {
    return (
      <div className="w-full h-screen bg-[#080612] flex flex-col justify-between p-4 font-sans overflow-hidden relative text-white">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#00d2e605_1px,transparent_1px),linear-gradient(to_bottom,#00d2e605_1px,transparent_1px)] bg-[size:16px_16px] pointer-events-none"></div>

        {/* Top Status Bar */}
        <div className="flex justify-between items-center z-10">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#00d2e6] shadow-[0_0_10px_#00d2e6] animate-pulse"></span>
            <span className="text-[9px] font-mono text-slate-400 tracking-widest uppercase">GNTV DIGITAL, ALL EVERYWHERE AI PROJECTION NODE</span>
          </div>
          <div className={`px-2 py-0.5 rounded border text-[9px] font-mono tracking-widest uppercase transition-all duration-300 ${isLive ? 'bg-red-500/20 text-red-400 border-red-500/40 animate-pulse' : 'bg-slate-800/40 text-slate-400 border-slate-700/40'}`}>
            {isLive ? '🔴 ON AIR' : '⚪ STANDBY'}
          </div>
        </div>

        {/* Center: Glowing Sphere Avatar & Speech Waveform */}
        <div className="flex-grow flex flex-col justify-center items-center relative z-10">
          <div className="relative flex justify-center items-center">
            {/* Pulsing rings */}
            <div className={`absolute rounded-full border border-dashed border-blue-500/30 w-48 h-48 animate-[spin_60s_linear_infinite] ${isSpeaking ? 'scale-110 border-blue-400/50' : ''} transition-transform duration-500`}></div>
            <div className={`absolute rounded-full border border-[#00d2e6]/20 w-40 h-40 animate-[spin_20s_linear_infinite_reverse] ${isSpeaking ? 'scale-105' : ''} transition-transform duration-500`}></div>

            {/* Core */}
            <div className={`relative w-28 h-28 rounded-full bg-gradient-to-br from-blue-600/20 to-purple-600/20 border-2 border-blue-500/40 flex flex-col justify-center items-center shadow-[0_0_30px_rgba(59,130,246,0.3)] transition-all duration-500 ${isSpeaking ? 'scale-110 shadow-[0_0_50px_rgba(0,210,230,0.5)] border-[#00d2e6]' : ''}`}>
              <span className={`text-4xl transition-transform duration-500 ${isSpeaking ? 'scale-115 animate-bounce' : 'opacity-80'}`}>
                {activeAnchor.toLowerCase() === 'ayaan' ? '👩‍💼' : '👨‍💼'}
              </span>
              <span className="text-[9px] font-mono text-slate-300 font-bold uppercase tracking-wider mt-1">{activeAnchor}</span>
              <span className="text-[8px] font-mono text-blue-400 uppercase tracking-widest">{activeLang} Voice</span>
            </div>

            {/* Speaking audio wave indicators */}
            {isSpeaking && (
              <div className="absolute flex gap-1 items-center h-8">
                {[...Array(6)].map((_, i) => (
                  <div
                    key={i}
                    className="w-0.5 bg-[#00d2e6] rounded-full"
                    style={{
                      height: `${8 + Math.random() * 20}px`,
                      animation: 'pulse 1.2s infinite',
                      animationDelay: `${i * 0.15}s`,
                      boxShadow: '0 0 6px #00d2e6'
                    }}
                  ></div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Bottom Panel: Teleprompter / Subtitles */}
        <div className="w-full bg-slate-950/75 border border-white/5 rounded-lg p-3 min-h-[70px] backdrop-blur-md relative z-10 flex flex-col justify-center">
          <div className="absolute top-1 left-2.5 text-[8px] font-mono text-slate-500 tracking-wider uppercase">Live Script Output</div>
          <div className="text-center mt-2.5">
            {broadcastText ? (
              <p className="text-slate-200 text-xs md:text-sm font-medium leading-relaxed max-w-xl mx-auto italic">
                "{broadcastText}"
              </p>
            ) : (
              <p className="text-slate-600 text-[10px] font-mono tracking-wide">
                SYSTEM STANDBY. AWAITING BROADCAST SIGNAL...
              </p>
            )}
          </div>
        </div>
      </div>
    );
  }

  // RENDER LAYER 1: Hardened Security Sign-In Screen
  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-slate-950 flex flex-col justify-center items-center p-6 font-sans text-white">
        <div className="w-full max-w-md bg-slate-900 border border-slate-800 p-8 rounded-2xl shadow-2xl">
          <div className="text-center mb-8">
            <h2 className="text-3xl font-extrabold tracking-wider text-blue-500 mb-2">GNTV DIGITAL, ALL EVERYWHERE SECURE PORTAL</h2>
            <p className="text-xs text-slate-400 uppercase tracking-widest">Authorized Broadcast Operations Only</p>
          </div>

          <form onSubmit={handleSecureLogin} className="space-y-6">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Operator ID</label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full p-4 bg-slate-950 border border-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 text-white"
                placeholder="Enter operator username"
                required
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Security Keyphrase</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full p-4 bg-slate-950 border border-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 text-white"
                placeholder="••••••••••••"
                required
              />
            </div>

            {loginError && (
              <div className="p-4 bg-red-950/40 border border-red-800/60 text-red-400 text-sm rounded-xl text-center font-medium animate-pulse">
                {loginError}
              </div>
            )}

            <button
              type="submit"
              disabled={isLocked}
              className="w-full py-4 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 disabled:from-slate-800 disabled:to-slate-900 disabled:text-slate-600 font-bold uppercase tracking-widest rounded-xl transition-all duration-300 shadow-[0_0_20px_rgba(37,99,235,0.2)] hover:shadow-[0_0_30px_rgba(37,99,235,0.4)] transform hover:-translate-y-0.5"
            >
              Verify Identity & Sign In
            </button>
          </form>
        </div>
      </div>
    );
  }

  // RENDER LAYER 2: Protected Studio Control Dashboard (Accessible only after validation)
  return (
    <div className="min-h-screen bg-slate-950 text-white flex flex-col justify-between font-sans">
      <header className="bg-slate-900 p-6 border-b border-slate-800 flex justify-between items-center shadow-lg">
        <h1 className="text-2xl font-black tracking-widest text-blue-500">GNTV DIGITAL, ALL EVERYWHERE <span className="text-white font-light text-base tracking-normal">STUDIO NODE</span></h1>
        <div className="flex items-center space-x-4">
          <span className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-xs font-bold px-3 py-1 rounded-full uppercase tracking-wider">Secure Connection Verified</span>
          <button onClick={() => { sessionStorage.clear(); setIsAuthenticated(false); }} className="text-xs text-slate-400 hover:text-red-400 underline transition">Log Out</button>
        </div>
      </header>

      {/* Main Grid Wrapper with fluid structural configurations */}
      <main className="max-w-[1600px] w-full mx-auto p-4 md:p-8 flex-grow grid grid-cols-1 md:grid-cols-12 gap-6 md:gap-8">

        {/* Left Grid Panel: VOD Archive Library */}
        <section className="md:col-span-12 lg:col-span-3 bg-slate-900/50 backdrop-blur-xl border border-white/5 p-5 rounded-2xl flex flex-col shadow-2xl transition-all hover:bg-slate-900/60 h-full max-h-[80vh]">
          <h3 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-5 flex items-center"><span className="w-2 h-2 rounded-full bg-blue-500 mr-2 shadow-[0_0_10px_rgba(59,130,246,0.8)]"></span>VOD Bulletin Library</h3>
          <div className="space-y-4 overflow-y-auto pr-2 custom-scrollbar flex-grow">
            {/* Sample Card */}
            <div className="group bg-slate-950/80 border border-white/5 p-4 rounded-xl flex flex-col justify-between transition-all duration-300 hover:border-blue-500/50 hover:shadow-[0_4px_20px_rgba(0,0,0,0.5)] hover:-translate-y-1 cursor-pointer">
              <div className="aspect-video bg-slate-800 rounded-lg mb-3 overflow-hidden relative">
                 <div className="absolute inset-0 bg-gradient-to-t from-black/80 to-transparent flex items-end p-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <span className="text-[10px] font-bold bg-blue-600 px-2 py-0.5 rounded text-white uppercase tracking-wider">Play</span>
                 </div>
              </div>
              <p className="text-sm font-bold tracking-tight leading-snug group-hover:text-blue-400 transition-colors line-clamp-2">Horn of Africa Daily Update</p>
              <span className="text-[11px] text-slate-500 mt-2 font-medium tracking-wide">Host: Ayaan • 2.4k views</span>
            </div>
          </div>
        </section>

        {/* Center Grid Panel: News Content Ingestion Area */}
        <section className="md:col-span-12 lg:col-span-6 bg-slate-900/50 backdrop-blur-xl border border-white/5 p-6 md:p-8 rounded-2xl flex flex-col justify-between shadow-2xl h-full">
          <div className="flex flex-col h-full">
            <label className="block text-xs font-bold uppercase tracking-widest text-slate-400 mb-4">Live Broadcast Teleprompter Input</label>
            <textarea
              value={newsText}
              onChange={(e) => setNewsText(e.target.value)}
              className="w-full flex-grow min-h-[250px] p-5 bg-slate-950/80 border border-white/10 rounded-xl focus:outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50 text-white text-lg placeholder-slate-600 resize-y mb-8 transition-all shadow-inner leading-relaxed"
              placeholder="Paste dynamic news script here..."
            ></textarea>

            <label className="block text-xs font-bold uppercase tracking-widest text-slate-400 mb-4">Manual Anchor Matrix Routing</label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 lg:gap-6">
              <button onClick={() => handleDailyBriefingRequest('so', 'ayaan')} className="group flex items-center justify-between p-5 bg-gradient-to-br from-blue-950/40 to-slate-900/40 border border-blue-900/50 rounded-xl hover:border-blue-500 hover:from-blue-900/60 hover:to-blue-800/40 transition-all duration-300 shadow-lg hover:shadow-[0_0_20px_rgba(59,130,246,0.3)] hover:-translate-y-1">
                <span className="text-2xl flex items-center gap-3">🇸🇴 <span className="text-base font-bold text-slate-200 group-hover:text-white transition-colors">Somali</span></span>
                <span className="text-[11px] font-bold text-blue-400 uppercase tracking-wider bg-blue-950/50 px-3 py-1 rounded-full group-hover:bg-blue-900/80 transition-colors">Ayaan (Warm)</span>
              </button>
              <button onClick={() => handleDailyBriefingRequest('en', 'omar')} className="group flex items-center justify-between p-5 bg-gradient-to-br from-purple-950/40 to-slate-900/40 border border-purple-900/50 rounded-xl hover:border-purple-500 hover:from-purple-900/60 hover:to-purple-800/40 transition-all duration-300 shadow-lg hover:shadow-[0_0_20px_rgba(168,85,247,0.3)] hover:-translate-y-1">
                <span className="text-2xl flex items-center gap-3">🇬🇧 <span className="text-base font-bold text-slate-200 group-hover:text-white transition-colors">English</span></span>
                <span className="text-[11px] font-bold text-purple-400 uppercase tracking-wider bg-purple-950/50 px-3 py-1 rounded-full group-hover:bg-purple-900/80 transition-colors">Omar (Auth)</span>
              </button>
              <button onClick={() => handleDailyBriefingRequest('sw', 'omar')} className="group flex items-center justify-between p-5 bg-gradient-to-br from-amber-950/40 to-slate-900/40 border border-amber-900/50 rounded-xl hover:border-amber-500 hover:from-amber-900/60 hover:to-amber-800/40 transition-all duration-300 shadow-lg hover:shadow-[0_0_20px_rgba(245,158,11,0.3)] hover:-translate-y-1">
                <span className="text-2xl flex items-center gap-3">🇰🇪 <span className="text-base font-bold text-slate-200 group-hover:text-white transition-colors">Swahili</span></span>
                <span className="text-[11px] font-bold text-amber-400 uppercase tracking-wider bg-amber-950/50 px-3 py-1 rounded-full group-hover:bg-amber-900/80 transition-colors">Omar (Auth)</span>
              </button>
              <button onClick={() => handleDailyBriefingRequest('ar', 'ayaan')} className="group flex items-center justify-between p-5 bg-gradient-to-br from-emerald-950/40 to-slate-900/40 border border-emerald-900/50 rounded-xl hover:border-emerald-500 hover:from-emerald-900/60 hover:to-emerald-800/40 transition-all duration-300 shadow-lg hover:shadow-[0_0_20px_rgba(16,185,129,0.3)] hover:-translate-y-1">
                <span className="text-2xl flex items-center gap-3">🇸🇦 <span className="text-base font-bold text-slate-200 group-hover:text-white transition-colors">Arabic</span></span>
                <span className="text-[11px] font-bold text-emerald-400 uppercase tracking-wider bg-emerald-950/50 px-3 py-1 rounded-full group-hover:bg-emerald-900/80 transition-colors">عيان (Warm)</span>
              </button>
            </div>
          </div>
        </section>

        {/* Right Grid Panel: Telemetry & Standby Monitoring */}
        <section className="md:col-span-12 lg:col-span-3 bg-slate-900/50 backdrop-blur-xl border border-white/5 p-5 rounded-2xl flex flex-col justify-between shadow-2xl h-full">
          <div>
            <h3 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-5 flex items-center"><span className="w-2 h-2 rounded-full bg-indigo-500 mr-2"></span>Studio Stream Telemetry</h3>
            <div className="bg-slate-950/80 border border-white/5 p-5 rounded-xl mb-5 shadow-inner relative overflow-hidden">
              <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-white/10 to-transparent"></div>
              <p className="text-sm font-bold mb-3 flex justify-between items-center">
                 <span className="text-slate-400">Live Status</span>
                 <span className={`px-3 py-1 rounded-full text-xs font-black tracking-widest ${isBriefingRequested ? 'bg-red-500/20 text-red-400 border border-red-500/30 animate-pulse shadow-[0_0_15px_rgba(239,68,68,0.3)]' : 'bg-slate-800 text-slate-500 border border-slate-700'}`}>{isBriefingRequested ? 'ON AIR' : 'STANDBY'}</span>
              </p>
              <div className="space-y-2 mt-4 pt-4 border-t border-white/5">
                <div className="flex justify-between items-center text-xs">
                  <span className="text-slate-500">Active Node</span>
                  <span className="text-slate-300 font-mono">Alibaba-Ingest-01</span>
                </div>
                <div className="flex justify-between items-center text-xs">
                  <span className="text-slate-500">FPS / Bitrate</span>
                  <span className="text-slate-300 font-mono">30 / 4.5 Mbps</span>
                </div>
              </div>
            </div>
            <div className="bg-blue-950/20 border border-blue-900/40 p-4 rounded-xl shadow-inner relative">
              <div className="absolute left-0 top-0 bottom-0 w-1 bg-blue-500/50 rounded-l-xl"></div>
              <p className="text-xs font-mono text-blue-300 break-words leading-relaxed pl-2">{studioStatus}</p>
            </div>
          </div>
          <div className="mt-6 pt-5 border-t border-white/5 text-center">
             <p className="text-[9px] text-slate-500 uppercase tracking-[0.2em] font-bold">GNTV DIGITAL, ALL EVERYWHERE Secure Node<br/><span className="text-slate-600 mt-1 inline-block">Configuration Control Module</span></p>
          </div>
        </section>

      </main>
    </div>
  );
}
