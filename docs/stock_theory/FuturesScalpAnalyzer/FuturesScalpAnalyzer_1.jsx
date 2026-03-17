import { useState, useMemo, useCallback, useEffect } from "react";

/* ═══════════════════════════════════════════════════════════════════════
   UTILITIES
   ═══════════════════════════════════════════════════════════════════════ */
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const fmt = (v, d = 2) => (isNaN(v) || !isFinite(v) ? "—" : v.toFixed(d));
const fmtUSD = (v) => isNaN(v) || !isFinite(v) ? "—" : "$" + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtPct = (v) => (isNaN(v) || !isFinite(v) ? "—" : (v * 100).toFixed(1) + "%");

function normCDF(z) {
  if (z < -6) return 0; if (z > 6) return 1;
  const a1=0.254829592,a2=-0.284496736,a3=1.421413741,a4=-1.453152027,a5=1.061405429,p=0.3275911;
  const s = z < 0 ? -1 : 1, x = Math.abs(z)/Math.SQRT2, t = 1/(1+p*x);
  return 0.5*(1+s*(1-((((a5*t+a4)*t+a3)*t+a2)*t+a1)*t*Math.exp(-x*x)));
}

/* ═══════════════════════════════════════════════════════════════════════
   STATISTICS FROM PRICE ARRAY
   ═══════════════════════════════════════════════════════════════════════ */
function calcStats(prices, maPeriod = 20) {
  if (!prices || prices.length < 3) return null;
  const n = prices.length;

  // MA — use last `maPeriod` prices (or all if fewer)
  const maSlice = prices.slice(-maPeriod);
  const ma = maSlice.reduce((a, b) => a + b, 0) / maSlice.length;

  // Standard Deviation (population) of same slice
  const variance = maSlice.reduce((acc, p) => acc + Math.pow(p - ma, 2), 0) / maSlice.length;
  const stdDev = Math.sqrt(variance);

  // ATR approximation from close-to-close (True Range proxy)
  // TR ≈ |Close[i] - Close[i-1]| when we only have closes
  const trs = [];
  for (let i = 1; i < n; i++) {
    trs.push(Math.abs(prices[i] - prices[i - 1]));
  }
  const atrSlice = trs.slice(-Math.min(14, trs.length));
  const atr = atrSlice.length > 0 ? atrSlice.reduce((a, b) => a + b, 0) / atrSlice.length : 0;

  return { ma: Math.round(ma * 100) / 100, stdDev: Math.round(stdDev * 100) / 100, atr: Math.round(atr * 100) / 100, count: n, maPeriod: maSlice.length };
}

function parsePrices(text) {
  if (!text.trim()) return [];
  // Support: comma, space, newline, tab, semicolon separated
  const tokens = text.split(/[,\s;|\t\n]+/).map(s => s.trim()).filter(Boolean);
  const nums = tokens.map(Number).filter(n => !isNaN(n) && n > 0);
  return nums;
}

/* ═══════════════════════════════════════════════════════════════════════
   ASSET CONFIG
   ═══════════════════════════════════════════════════════════════════════ */
const ASSETS = {
  ES:  { label:"E-mini S&P 500", tick:0.25, tickVal:12.50, ptVal:50 },
  MES: { label:"Micro E-mini S&P",tick:0.25, tickVal:1.25,  ptVal:5 },
};

/* ═══════════════════════════════════════════════════════════════════════
   CALCULATION ENGINE
   ═══════════════════════════════════════════════════════════════════════ */
function useEngine(inputs) {
  return useMemo(() => {
    const { asset,currentPrice,ma,stdDev,atr,atrMult,winRate,avgWin,avgLoss,slippage,commission,accountBalance,riskPct,spotPrice,futuresPrice } = inputs;
    const cfg = ASSETS[asset];
    const z = stdDev > 0 ? (currentPrice - ma) / stdDev : 0;
    const pVal = normCDF(-Math.abs(z)) * 2;
    const zSignal = z < -2 ? "STRONG LONG" : z > 2 ? "STRONG SHORT" : z < -1.5 ? "LEAN LONG" : z > 1.5 ? "LEAN SHORT" : "NEUTRAL";
    const zColor = z < -2 ? "#00e676" : z > 2 ? "#ff1744" : z < -1.5 ? "#69f0ae" : z > 1.5 ? "#ff8a80" : "#78909c";
    const p = winRate / 100, q = 1 - p;
    const grossEV = p * avgWin - q * avgLoss;
    const friction = slippage + (commission / cfg.tickVal);
    const netEV = grossEV - friction;
    const netEVusd = netEV * cfg.tickVal;
    const b = avgLoss > 0 ? avgWin / avgLoss : 0;
    const kelly = b > 0 ? (b * p - q) / b : 0;
    const halfKelly = kelly / 2;
    const conviction = kelly <= 0 ? "NO EDGE" : halfKelly < 0.02 ? "VERY LOW" : halfKelly < 0.05 ? "LOW" : halfKelly < 0.1 ? "MODERATE" : halfKelly < 0.2 ? "HIGH" : "VERY HIGH";
    const atrStop = atr * atrMult;
    const isLong = z <= 0;
    const sl = isLong ? currentPrice - atrStop : currentPrice + atrStop;
    const riskPerContract = atrStop * cfg.ptVal;
    const riskBudget = accountBalance * (riskPct / 100);
    const maxContracts = riskPerContract > 0 ? Math.floor(riskBudget / riskPerContract) : 0;
    const recContracts = Math.min(maxContracts, 2);
    const tp15 = isLong ? currentPrice + atrStop*1.5 : currentPrice - atrStop*1.5;
    const tp2  = isLong ? currentPrice + atrStop*2   : currentPrice - atrStop*2;
    const tp3  = isLong ? currentPrice + atrStop*3   : currentPrice - atrStop*3;
    const basis = futuresPrice - spotPrice;
    const basisPct = spotPrice > 0 ? (basis / spotPrice) * 100 : 0;
    const basisState = basis > 2 ? "CONTANGO" : basis < -2 ? "BACKWARDATION" : "FAIR VALUE";
    const pnlTP1 = Math.abs(tp15 - currentPrice) * cfg.ptVal * Math.max(recContracts,1);
    const pnlSL  = atrStop * cfg.ptVal * Math.max(recContracts,1);
    const checks = [
      { label:"Z-Score 방향성", pass: Math.abs(z) >= 1.5, val:`Z = ${fmt(z)}` },
      { label:"순 기대값 > 0",  pass: netEV > 0,          val:`${fmt(netEV)}t (${fmtUSD(Math.abs(netEVusd))})` },
      { label:"Kelly 양수",     pass: kelly > 0,           val:fmtPct(kelly) },
      { label:"손익비 >= 1.5",   pass: b >= 1.5,            val:`${fmt(b,1)}:1` },
    ];
    const passN = checks.filter(c=>c.pass).length;
    const verdict = passN === 4 ? "GO" : passN >= 3 ? "CAUTION" : "NO ENTRY";
    return { cfg,z,pVal,zSignal,zColor,p,q,b,grossEV,friction,netEV,netEVusd,kelly,halfKelly,conviction,atrStop,isLong,sl,riskPerContract,riskBudget,maxContracts,recContracts,tp15,tp2,tp3,basis,basisPct,basisState,pnlTP1,pnlSL,checks,passN,verdict };
  }, [inputs]);
}

/* ═══════════════════════════════════════════════════════════════════════
   DESIGN TOKENS
   ═══════════════════════════════════════════════════════════════════════ */
const F = { mono:"'IBM Plex Mono','Fira Code',monospace", sans:"'DM Sans','Manrope',-apple-system,sans-serif" };
const K = { bg0:"#060910",bg1:"#0b0f18",bg2:"#101520",bg3:"#161c2a",brd:"#1c2336",brdL:"#273048",txt:"#dfe3ed",dim:"#6b7594",mut:"#3e4868",acc:"#3b82f6",grn:"#00e676",red:"#ff1744",cyn:"#4fc3f7",org:"#ffab40",ylw:"#fdd835" };
const boxBase = { background:`linear-gradient(145deg,${K.bg2},${K.bg3})`, border:`1px solid ${K.brd}`, borderRadius:10, padding:18, marginBottom:14 };

/* ═══════════════════════════════════════════════════════════════════════
   ATOMS
   ═══════════════════════════════════════════════════════════════════════ */
function NIn({ label,value,onChange,unit,step=1,min,help,disabled,highlight }) {
  return (
    <div style={{ marginBottom:13 }}>
      <label style={{ display:"block",fontSize:9.5,fontFamily:F.mono,color:highlight?K.acc:K.dim,textTransform:"uppercase",letterSpacing:"0.1em",marginBottom:3 }}>
        {label} {highlight && <span style={{fontSize:8,color:K.grn}}>● AUTO</span>}
      </label>
      <div style={{ display:"flex",gap:5,alignItems:"center" }}>
        <input type="number" value={value} step={step} min={min} disabled={disabled}
          onChange={e=>onChange(parseFloat(e.target.value)||0)}
          style={{ width:"100%",padding:"6px 9px",background:disabled?K.bg1:K.bg0,border:`1px solid ${highlight?`${K.acc}50`:K.brd}`,borderRadius:5,color:disabled?K.dim:K.txt,fontSize:12.5,fontFamily:F.mono,outline:"none",opacity:disabled?0.6:1 }}
          onFocus={e=>{if(!disabled)e.target.style.borderColor=K.acc}} onBlur={e=>{e.target.style.borderColor=highlight?`${K.acc}50`:K.brd}} />
        {unit && <span style={{ fontSize:9.5,color:K.mut,fontFamily:F.mono,whiteSpace:"nowrap" }}>{unit}</span>}
      </div>
      {help && <span style={{ fontSize:8.5,color:K.mut,marginTop:1,display:"block" }}>{help}</span>}
    </div>
  );
}

function Pill({ children,color=K.dim }) {
  return <span style={{ display:"inline-block",padding:"2px 9px",borderRadius:4,background:`${color}15`,border:`1px solid ${color}35`,color,fontSize:10.5,fontWeight:700,fontFamily:F.mono,letterSpacing:"0.04em" }}>{children}</span>;
}

function Met({ label,value,sub,color,big }) {
  return (
    <div style={{ flex:1,minWidth:big?130:100 }}>
      <div style={{ fontSize:9,color:K.mut,fontFamily:F.mono,textTransform:"uppercase",letterSpacing:"0.1em",marginBottom:4 }}>{label}</div>
      <div style={{ fontSize:big?24:18,fontWeight:700,color:color||K.txt,fontFamily:F.mono,lineHeight:1.15 }}>{value}</div>
      {sub && <div style={{ fontSize:9.5,color:K.dim,marginTop:3,fontFamily:F.mono }}>{sub}</div>}
    </div>
  );
}

function Sec({ icon,title,tag,tagC }) {
  return (
    <div style={{ display:"flex",alignItems:"center",gap:8,marginBottom:14,paddingBottom:9,borderBottom:`1px solid ${K.brd}` }}>
      <span style={{ fontSize:15 }}>{icon}</span>
      <span style={{ fontSize:13.5,fontWeight:700,color:K.txt,fontFamily:F.sans }}>{title}</span>
      {tag && <Pill color={tagC||K.acc}>{tag}</Pill>}
    </div>
  );
}

function ZBar({ z }) {
  const pct = clamp((z+4)/8*100,2,98);
  const col = z<-2?K.grn:z>2?K.red:z<-1?"#69f0ae":z>1?"#ff8a80":"#78909c";
  return (
    <div style={{ marginTop:12 }}>
      <div style={{ position:"relative",height:10,background:K.bg0,borderRadius:5 }}>
        <div style={{ position:"absolute",left:0,width:"25%",height:"100%",background:`${K.grn}0c`,borderRadius:"5px 0 0 5px" }} />
        <div style={{ position:"absolute",right:0,width:"25%",height:"100%",background:`${K.red}0c`,borderRadius:"0 5px 5px 0" }} />
        {[12.5,25,37.5,50,62.5,75,87.5].map((p,i)=><div key={i} style={{ position:"absolute",left:`${p}%`,top:0,bottom:0,width:1,background:K.brd }} />)}
        <div style={{ position:"absolute",left:`${pct}%`,top:"50%",transform:"translate(-50%,-50%)",width:14,height:14,borderRadius:"50%",background:col,boxShadow:`0 0 12px ${col}90`,transition:"left 0.35s cubic-bezier(.4,0,.2,1)" }} />
      </div>
      <div style={{ display:"flex",justifyContent:"space-between",marginTop:4,fontSize:8.5,color:K.mut,fontFamily:F.mono }}>
        <span>-4σ</span><span>-2σ</span><span>μ</span><span>+2σ</span><span>+4σ</span>
      </div>
    </div>
  );
}

function EVBar({ gross,net,max=8 }) {
  const nP = clamp(net/max*50,-50,50);
  return (
    <div style={{ marginTop:10 }}>
      <div style={{ display:"flex",gap:10,marginBottom:6,fontSize:9,fontFamily:F.mono }}>
        <span style={{ color:K.dim }}>Gross: <span style={{ color:gross>=0?K.grn:K.red }}>{fmt(gross)}t</span></span>
        <span style={{ color:K.dim }}>Friction: <span style={{ color:K.org }}>-{fmt(gross-net)}t</span></span>
        <span style={{ color:K.dim }}>Net: <span style={{ color:net>=0?K.grn:K.red,fontWeight:700 }}>{fmt(net)}t</span></span>
      </div>
      <div style={{ position:"relative",height:7,background:K.bg0,borderRadius:4 }}>
        <div style={{ position:"absolute",left:"50%",top:0,bottom:0,width:1,background:K.brdL }} />
        <div style={{ position:"absolute",top:0,height:"100%",borderRadius:4,left:nP>=0?"50%":`${50+nP}%`,width:`${Math.abs(nP)}%`,background:nP>=0?K.grn:K.red,transition:"all 0.3s" }} />
      </div>
    </div>
  );
}

function KGauge({ hk,conv }) {
  const pct = clamp(hk*100/25,0,100);
  const col = conv==="NO EDGE"?K.red:(conv==="VERY LOW"||conv==="LOW")?K.org:conv==="MODERATE"?K.ylw:K.grn;
  return (
    <div style={{ marginTop:10 }}>
      <div style={{ position:"relative",height:7,background:K.bg0,borderRadius:4 }}>
        <div style={{ height:"100%",borderRadius:4,width:`${pct}%`,background:`linear-gradient(90deg,${col}50,${col})`,transition:"width 0.4s" }} />
      </div>
      <div style={{ display:"flex",justifyContent:"space-between",alignItems:"center",marginTop:5 }}>
        <span style={{ fontSize:8.5,color:K.mut,fontFamily:F.mono }}>0%</span>
        <Pill color={col}>{conv}</Pill>
        <span style={{ fontSize:8.5,color:K.mut,fontFamily:F.mono }}>25%</span>
      </div>
    </div>
  );
}

function RRVis({ entry,sl,tp15,tp2,tp3 }) {
  const all=[sl,entry,tp15,tp2,tp3], lo=Math.min(...all), hi=Math.max(...all), rng=hi-lo||1, pad=rng*0.15;
  const toY=p=>clamp(((hi+pad-p)/(rng+pad*2))*170,5,165);
  const lines=[
    {p:sl,lb:"STOP",c:K.red,d:true},{p:entry,lb:"ENTRY",c:K.acc,d:false},
    {p:tp15,lb:"1.5R",c:"#69f0ae",d:true},{p:tp2,lb:"2R",c:K.grn,d:true},{p:tp3,lb:"3R",c:K.grn,d:false},
  ];
  return (
    <div style={{ background:K.bg0,borderRadius:8,padding:"10px 6px",marginTop:10 }}>
      <svg width="100%" height="180" viewBox="0 0 310 180" style={{ display:"block" }}>
        <rect x="48" y={Math.min(toY(entry),toY(sl))} width="195" height={Math.abs(toY(sl)-toY(entry))} fill={`${K.red}0e`} rx="3"/>
        <rect x="48" y={Math.min(toY(entry),toY(tp3))} width="195" height={Math.abs(toY(tp3)-toY(entry))} fill={`${K.grn}08`} rx="3"/>
        {lines.map((l,i)=>(
          <g key={i}>
            <line x1="48" y1={toY(l.p)} x2="262" y2={toY(l.p)} stroke={l.c} strokeWidth={l.d?1.2:2} strokeDasharray={l.d?"5,4":"none"} />
            <text x="44" y={toY(l.p)+3.5} textAnchor="end" fill={l.c} fontSize="8.5" fontFamily="monospace" fontWeight={l.d?400:700}>{l.lb}</text>
            <text x="266" y={toY(l.p)+3.5} textAnchor="start" fill={l.c} fontSize="8.5" fontFamily="monospace">{fmt(l.p,2)}</text>
          </g>
        ))}
      </svg>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   SAMPLE DATA (for demo/testing)
   ═══════════════════════════════════════════════════════════════════════ */
const SAMPLE_ES = "5872.50, 5878.25, 5865.00, 5880.75, 5889.50, 5895.25, 5887.00, 5892.75, 5901.50, 5898.00, 5905.25, 5910.75, 5903.50, 5908.00, 5915.25, 5911.50, 5918.75, 5922.00, 5916.50, 5920.00";

/* ═══════════════════════════════════════════════════════════════════════
   MAIN APP
   ═══════════════════════════════════════════════════════════════════════ */
export default function FuturesScalpAnalyzer() {
  const [asset,setAsset] = useState("ES");
  const cfg = ASSETS[asset];

  // Price history input
  const [priceText, setPriceText] = useState(SAMPLE_ES);
  const [maPeriod, setMaPeriod] = useState(20);
  const [autoMode, setAutoMode] = useState(true);

  // Parsed prices & auto-computed stats
  const prices = useMemo(() => parsePrices(priceText), [priceText]);
  const autoStats = useMemo(() => calcStats(prices, maPeriod), [prices, maPeriod]);

  // Core inputs
  const [inputs, setInputs] = useState({
    currentPrice: 5920,
    ma: 5900, stdDev: 15, atr: 12,
    atrMult: 1.0,
    winRate: 58, avgWin: 6, avgLoss: 4, slippage: 0.5, commission: 2.25,
    accountBalance: 10000, riskPct: 2,
    spotPrice: 5918, futuresPrice: 5920,
  });
  const s = useCallback((k) => (v) => setInputs(p => ({ ...p, [k]: v })), []);

  // Auto-sync: when autoMode is on and we have valid stats, push them into inputs
  useEffect(() => {
    if (autoMode && autoStats) {
      setInputs(p => ({
        ...p,
        currentPrice: prices[prices.length - 1], // latest price = current
        ma: autoStats.ma,
        stdDev: autoStats.stdDev,
        atr: autoStats.atr,
        futuresPrice: prices[prices.length - 1],
      }));
    }
  }, [autoMode, autoStats, prices]);

  const calc = useEngine({ ...inputs, asset });

  const switchAsset = (a) => { setAsset(a); };

  const vc = calc.verdict === "GO" ? K.grn : calc.verdict === "CAUTION" ? K.ylw : K.red;

  return (
    <div style={{ minHeight: "100vh", background: K.bg0, color: K.txt, fontFamily: F.sans }}>
      {/* HEADER */}
      <div style={{ background: `linear-gradient(180deg,${K.bg1},${K.bg0})`, borderBottom: `1px solid ${K.brd}`, padding: "14px 18px" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 34, height: 34, borderRadius: 8, background: `linear-gradient(135deg,${K.acc},#1d4ed8)`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 17, fontWeight: 900, color: "#fff", fontFamily: F.mono }}>Σ</div>
            <div>
              <div style={{ fontSize: 15, fontWeight: 800, letterSpacing: "-0.02em" }}>Futures Scalp Analyzer</div>
              <div style={{ fontSize: 9, color: K.dim, fontFamily: F.mono, letterSpacing: "0.06em" }}>PROBABILITY-BASED DECISION ENGINE v1.1</div>
            </div>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            {Object.entries(ASSETS).map(([k, v]) => (
              <button key={k} onClick={() => switchAsset(k)} style={{
                padding: "6px 14px", borderRadius: 6, border: `1px solid ${asset === k ? K.acc : K.brd}`,
                background: asset === k ? `${K.acc}20` : K.bg2, color: asset === k ? K.acc : K.dim,
                fontSize: 11, fontWeight: 700, fontFamily: F.mono, cursor: "pointer", transition: "all 0.2s"
              }}>{k}<span style={{ fontSize: 9, marginLeft: 4, opacity: 0.6 }}>${v.tickVal}/tick</span></button>
            ))}
          </div>
        </div>
      </div>

      {/* VERDICT STRIP */}
      <div style={{ background: `${vc}08`, borderBottom: `1px solid ${vc}25`, padding: "10px 18px", textAlign: "center" }}>
        <span style={{ fontSize: 12, fontWeight: 800, color: vc, fontFamily: F.mono, letterSpacing: "0.08em" }}>
          {calc.verdict === "GO" ? "✅" : calc.verdict === "CAUTION" ? "⚠️" : "🚫"}{" "}
          SIGNAL: {calc.verdict} — [{calc.passN}/4] — {calc.zSignal} — {calc.isLong ? "▲ LONG BIAS" : "▼ SHORT BIAS"}
        </span>
      </div>

      {/* BODY */}
      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "18px 18px 40px" }}>
        <div style={{ display: "flex", gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>

          {/* ══════════ LEFT: INPUTS ══════════ */}
          <div style={{ width: 280, flexShrink: 0 }}>

            {/* ── Price Data Input (NEW) ── */}
            <div style={{ ...boxBase, borderColor: autoMode ? `${K.acc}40` : K.brd }}>
              <Sec icon="📋" title="Price Data" tag={autoMode ? "AUTO" : "MANUAL"} tagC={autoMode ? K.grn : K.dim} />

              {/* Mode Toggle */}
              <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
                <button onClick={() => setAutoMode(true)} style={{
                  flex: 1, padding: "7px", borderRadius: 6, border: `1px solid ${autoMode ? K.acc : K.brd}`,
                  background: autoMode ? `${K.acc}15` : K.bg0, color: autoMode ? K.acc : K.dim,
                  fontSize: 10, fontWeight: 700, fontFamily: F.mono, cursor: "pointer"
                }}>AUTO 산출</button>
                <button onClick={() => setAutoMode(false)} style={{
                  flex: 1, padding: "7px", borderRadius: 6, border: `1px solid ${!autoMode ? K.org : K.brd}`,
                  background: !autoMode ? `${K.org}15` : K.bg0, color: !autoMode ? K.org : K.dim,
                  fontSize: 10, fontWeight: 700, fontFamily: F.mono, cursor: "pointer"
                }}>수동 입력</button>
              </div>

              {autoMode && (
                <>
                  <label style={{ display: "block", fontSize: 9.5, fontFamily: F.mono, color: K.dim, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 4 }}>
                    최근 종가 (콤마/줄바꿈 구분)
                  </label>
                  <textarea
                    value={priceText}
                    onChange={(e) => setPriceText(e.target.value)}
                    placeholder="예: 5880.50, 5885.25, 5890.00 ..."
                    rows={4}
                    style={{
                      width: "100%", padding: "8px 10px", background: K.bg0, border: `1px solid ${K.acc}40`,
                      borderRadius: 6, color: K.txt, fontSize: 11, fontFamily: F.mono, outline: "none",
                      resize: "vertical", lineHeight: 1.5, boxSizing: "border-box"
                    }}
                    onFocus={e => { e.target.style.borderColor = K.acc }}
                    onBlur={e => { e.target.style.borderColor = `${K.acc}40` }}
                  />
                  <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6, marginBottom: 10 }}>
                    <span style={{ fontSize: 9, color: prices.length >= 3 ? K.grn : K.red, fontFamily: F.mono }}>
                      {prices.length}개 가격 파싱됨 {prices.length < 3 && "(최소 3개 필요)"}
                    </span>
                    <button onClick={() => setPriceText(SAMPLE_ES)} style={{
                      fontSize: 9, color: K.acc, background: "none", border: "none", cursor: "pointer", fontFamily: F.mono, textDecoration: "underline"
                    }}>샘플 데이터</button>
                  </div>

                  <NIn label="MA 기간" value={maPeriod} onChange={setMaPeriod} step={1} min={2} help="이동평균 계산에 사용할 캔들 수" />

                  {/* Auto-computed stats display */}
                  {autoStats && (
                    <div style={{ background: K.bg0, borderRadius: 8, padding: "10px 12px", marginTop: 4 }}>
                      <div style={{ fontSize: 9, color: K.grn, fontFamily: F.mono, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 8 }}>
                        ● 자동 산출 결과
                      </div>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                        {[
                          { l: "현재가", v: fmt(prices[prices.length - 1], 2) },
                          { l: `MA(${autoStats.maPeriod})`, v: fmt(autoStats.ma, 2) },
                          { l: "σ (StdDev)", v: fmt(autoStats.stdDev, 2) },
                          { l: "ATR(14)≈", v: fmt(autoStats.atr, 2) },
                        ].map((item, i) => (
                          <div key={i}>
                            <div style={{ fontSize: 8.5, color: K.mut, fontFamily: F.mono }}>{item.l}</div>
                            <div style={{ fontSize: 14, fontWeight: 700, color: K.acc, fontFamily: F.mono }}>{item.v}</div>
                          </div>
                        ))}
                      </div>
                      <div style={{ marginTop: 8, fontSize: 8.5, color: K.mut, fontFamily: F.mono, lineHeight: 1.4 }}>
                        ⓘ ATR은 종가 간 변동폭(|C[i]-C[i-1]|) 14기간 평균으로 근사. OHLC 데이터 사용 시 더 정확.
                      </div>
                    </div>
                  )}
                </>
              )}

              {!autoMode && (
                <>
                  <NIn label="현재가 (Current)" value={inputs.currentPrice} onChange={s("currentPrice")} step={0.25} unit="pts" />
                  <NIn label="이동평균 (MA)" value={inputs.ma} onChange={s("ma")} step={0.25} unit="pts" />
                  <NIn label="표준편차 (σ)" value={inputs.stdDev} onChange={s("stdDev")} step={0.5} unit="pts" />
                  <NIn label="ATR (14)" value={inputs.atr} onChange={s("atr")} step={0.25} unit="pts" />
                </>
              )}

              <NIn label="ATR 배수 (Stop)" value={inputs.atrMult} onChange={s("atrMult")} step={0.1} min={0.1} help="스캘핑: 0.5~1.0 / 스윙: 1.5~2.0" />
            </div>

            {/* Backtest Stats */}
            <div style={boxBase}>
              <Sec icon="🎯" title="Backtest Stats" tag="EV INPUT" />
              <NIn label="승률 (Win Rate)" value={inputs.winRate} onChange={s("winRate")} step={1} unit="%" />
              <NIn label="평균 익절 (Avg Win)" value={inputs.avgWin} onChange={s("avgWin")} step={0.5} unit="ticks" />
              <NIn label="평균 손절 (Avg Loss)" value={inputs.avgLoss} onChange={s("avgLoss")} step={0.5} unit="ticks" />
              <NIn label="슬리피지" value={inputs.slippage} onChange={s("slippage")} step={0.25} unit="ticks" help="스캘핑 평균 0.25~0.5t" />
              <NIn label="수수료 (편도)" value={inputs.commission} onChange={s("commission")} step={0.05} unit="$" />
            </div>

            {/* Account */}
            <div style={boxBase}>
              <Sec icon="💰" title="Account" />
              <NIn label="계좌잔고" value={inputs.accountBalance} onChange={s("accountBalance")} step={100} unit="$" />
              <NIn label="허용 리스크" value={inputs.riskPct} onChange={s("riskPct")} step={0.5} min={0.1} unit="%" />
            </div>

            {/* Basis Spread Input */}
            <div style={boxBase}>
              <Sec icon="📉" title="Basis Spread" />
              <NIn label="현물 (SPX)" value={inputs.spotPrice} onChange={s("spotPrice")} step={0.25} unit="pts" />
              <NIn label="선물 (ES)" value={inputs.futuresPrice} onChange={s("futuresPrice")} step={0.25} unit="pts" />
            </div>
          </div>

          {/* ══════════ RIGHT: OUTPUTS ══════════ */}
          <div style={{ flex: 1, minWidth: 300 }}>

            {/* Decision Matrix */}
            <div style={{ ...boxBase, borderColor: `${vc}30` }}>
              <Sec icon="🎯" title="Decision Matrix" tag="ENTRY CHECKLIST" tagC={vc} />
              <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                {calc.checks.map((c, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 9, padding: "7px 11px", background: c.pass ? `${K.grn}08` : `${K.red}08`, border: `1px solid ${c.pass ? K.grn : K.red}20`, borderRadius: 6 }}>
                    <span style={{ width: 20, height: 20, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", background: c.pass ? `${K.grn}18` : `${K.red}18`, color: c.pass ? K.grn : K.red, fontSize: 11, fontWeight: 700 }}>{c.pass ? "✓" : "✗"}</span>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 11.5, fontWeight: 600, color: K.txt, fontFamily: F.mono }}>{c.label}</div>
                      <div style={{ fontSize: 9.5, color: K.dim, fontFamily: F.mono }}>{c.val}</div>
                    </div>
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 12, padding: "9px 14px", background: `${vc}0c`, border: `1px solid ${vc}30`, borderRadius: 6, textAlign: "center" }}>
                <span style={{ fontSize: 14, fontWeight: 800, color: vc, fontFamily: F.mono, letterSpacing: "0.06em" }}>
                  [{calc.passN}/4] {calc.verdict === "GO" ? "ALL CLEAR — 진입 가능" : calc.verdict === "CAUTION" ? "CAUTION — 조건부 진입" : "NO ENTRY — 대기"}
                </span>
              </div>
            </div>

            {/* Z-Score */}
            <div style={boxBase}>
              <Sec icon="📐" title="Z-Score Analysis" tag="통계적 위치" />
              <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
                <Met label="Z-Score" value={fmt(calc.z)} color={calc.zColor} big />
                <Met label="Signal" value={calc.zSignal} color={calc.zColor} />
                <Met label="P-Value" value={fmtPct(calc.pVal)} sub="양측검정" />
                <Met label="이격" value={fmt(inputs.currentPrice - inputs.ma, 1) + "p"} sub="vs MA" />
              </div>
              <ZBar z={calc.z} />
              <div style={{ marginTop: 12, padding: "8px 12px", background: K.bg0, borderRadius: 6, fontSize: 10, fontFamily: F.mono, color: K.dim, lineHeight: 1.6 }}>
                Z = ({inputs.currentPrice} − {inputs.ma}) / {inputs.stdDev} = <span style={{ color: calc.zColor, fontWeight: 700 }}>{fmt(calc.z)}</span>
                {" "}→ MA에서 {fmt(Math.abs(calc.z))}σ {calc.z < 0 ? "하방" : "상방"} | 이격 확률 {fmtPct(calc.pVal)}
              </div>
            </div>

            {/* EV Engine */}
            <div style={boxBase}>
              <Sec icon="⚡" title="Scalp EV Engine" tag="기대값" tagC={calc.netEV >= 0 ? K.grn : K.red} />
              <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
                <Met label="Net EV/Trade" value={`${calc.netEV >= 0 ? "+" : ""}${fmt(calc.netEV)}t`} color={calc.netEV >= 0 ? K.grn : K.red} big sub={`${calc.netEV >= 0 ? "+" : "-"} ${fmtUSD(Math.abs(calc.netEVusd))}`} />
                <Met label="Gross EV" value={`${fmt(calc.grossEV)}t`} sub="before cost" />
                <Met label="Friction" value={`${fmt(calc.friction)}t`} color={K.org} sub="slip+comm" />
                <Met label="R:R" value={`${fmt(calc.b, 1)}:1`} />
              </div>
              <EVBar gross={calc.grossEV} net={calc.netEV} />
              <div style={{ marginTop: 12, padding: "8px 12px", background: K.bg0, borderRadius: 6, fontSize: 10, fontFamily: F.mono, color: K.dim, lineHeight: 1.6 }}>
                EV = {fmtPct(calc.p)}×{inputs.avgWin} − {fmtPct(calc.q)}×{inputs.avgLoss} − {fmt(calc.friction)}t = <span style={{ color: calc.netEV >= 0 ? K.grn : K.red, fontWeight: 700 }}>{fmt(calc.netEV)}t</span>
                {calc.netEV > 0
                  ? <> | 100회 기대 순익: <span style={{ color: K.grn }}>+{fmtUSD(Math.abs(calc.netEVusd) * 100)}</span></>
                  : <> | ⚠ 반복매매 시 손실 누적</>}
              </div>
            </div>

            {/* Kelly + Position */}
            <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
              <div style={{ ...boxBase, flex: 1, minWidth: 250 }}>
                <Sec icon="🎰" title="Kelly Criterion" tag="확신도" tagC={calc.kelly > 0 ? K.grn : K.red} />
                <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
                  <Met label="Full Kelly" value={fmtPct(calc.kelly)} />
                  <Met label="Half Kelly" value={fmtPct(calc.halfKelly)} color={K.acc} sub="권장 배팅비중" big />
                </div>
                <KGauge hk={calc.halfKelly} conv={calc.conviction} />
                <div style={{ marginTop: 10, fontSize: 9.5, color: K.dim, fontFamily: F.mono }}>
                  f* = ({fmt(calc.b, 1)}×{fmtPct(calc.p)} − {fmtPct(calc.q)}) / {fmt(calc.b, 1)} = {fmtPct(calc.kelly)}
                </div>
              </div>
              <div style={{ ...boxBase, flex: 1, minWidth: 250 }}>
                <Sec icon="📏" title="Position Sizer" />
                <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
                  <Met label="리스크 예산" value={fmtUSD(calc.riskBudget)} sub={`잔고의 ${inputs.riskPct}%`} />
                  <Met label="계약당 위험" value={fmtUSD(calc.riskPerContract)} sub={`${fmt(calc.atrStop)}p × $${calc.cfg.ptVal}`} />
                </div>
                <div style={{ marginTop: 14, padding: "14px", background: K.bg0, borderRadius: 8, textAlign: "center" }}>
                  <div style={{ fontSize: 9, color: K.mut, fontFamily: F.mono, textTransform: "uppercase", marginBottom: 6 }}>권장 계약 수</div>
                  <div style={{ fontSize: 40, fontWeight: 800, color: K.acc, fontFamily: F.mono }}>{calc.recContracts}</div>
                  <div style={{ fontSize: 9.5, color: K.dim, fontFamily: F.mono, marginTop: 4 }}>최대 {calc.maxContracts}계약 / 스캘핑 2계약 상한</div>
                </div>
              </div>
            </div>

            {/* ATR + RR Map */}
            <div style={boxBase}>
              <Sec icon="🛡️" title="ATR Stop & R:R Map" tag={`ATR×${inputs.atrMult}`} />
              <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginBottom: 6 }}>
                <Met label="ATR Stop" value={`${fmt(calc.atrStop)}p`} sub={fmtUSD(calc.riskPerContract) + "/ct"} color={K.red} />
                <Met label="Stop" value={fmt(calc.sl, 2)} color={K.red} />
                <Met label="TP 1.5R" value={fmt(calc.tp15, 2)} color="#69f0ae" />
                <Met label="TP 2R" value={fmt(calc.tp2, 2)} color={K.grn} />
                <Met label="TP 3R" value={fmt(calc.tp3, 2)} color={K.grn} />
              </div>
              <RRVis entry={inputs.currentPrice} sl={calc.sl} tp15={calc.tp15} tp2={calc.tp2} tp3={calc.tp3} />
              <div style={{ display: "flex", gap: 10, marginTop: 12, flexWrap: "wrap" }}>
                <div style={{ flex: 1, padding: "8px 12px", background: `${K.grn}0a`, border: `1px solid ${K.grn}20`, borderRadius: 6, textAlign: "center" }}>
                  <div style={{ fontSize: 9, color: K.dim, fontFamily: F.mono }}>TP 1.5R P&L</div>
                  <div style={{ fontSize: 16, fontWeight: 700, color: K.grn, fontFamily: F.mono }}>+{fmtUSD(calc.pnlTP1)}</div>
                </div>
                <div style={{ flex: 1, padding: "8px 12px", background: `${K.red}0a`, border: `1px solid ${K.red}20`, borderRadius: 6, textAlign: "center" }}>
                  <div style={{ fontSize: 9, color: K.dim, fontFamily: F.mono }}>SL Hit P&L</div>
                  <div style={{ fontSize: 16, fontWeight: 700, color: K.red, fontFamily: F.mono }}>-{fmtUSD(calc.pnlSL)}</div>
                </div>
              </div>
            </div>

            {/* Basis Spread */}
            <div style={boxBase}>
              <Sec icon="📉" title="Basis Spread" tag={calc.basisState} tagC={calc.basis > 2 ? K.cyn : calc.basis < -2 ? K.org : "#78909c"} />
              <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
                <Met label="SPX (현물)" value={fmt(inputs.spotPrice, 2)} />
                <Met label="ES (선물)" value={fmt(inputs.futuresPrice, 2)} />
                <Met label="Basis" value={`${calc.basis >= 0 ? "+" : ""}${fmt(calc.basis, 2)}p`} color={calc.basis > 2 ? K.cyn : calc.basis < -2 ? K.org : "#78909c"} big />
                <Met label="Basis %" value={`${fmt(calc.basisPct, 3)}%`} />
              </div>
              <div style={{ marginTop: 12, position: "relative", height: 10, background: K.bg0, borderRadius: 5 }}>
                <div style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 1, background: K.brdL }} />
                {(() => { const bP = clamp((calc.basis + 20) / 40 * 100, 2, 98), bC = calc.basis > 2 ? K.cyn : calc.basis < -2 ? K.org : "#78909c";
                  return <div style={{ position: "absolute", left: `${bP}%`, top: "50%", transform: "translate(-50%,-50%)", width: 12, height: 12, borderRadius: "50%", background: bC, boxShadow: `0 0 10px ${bC}80`, transition: "left 0.35s" }} />;
                })()}
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: 8.5, color: K.mut, fontFamily: F.mono }}>
                <span>← BACKWARDATION</span><span>FAIR</span><span>CONTANGO →</span>
              </div>
              <div style={{ marginTop: 10, padding: "8px 12px", background: K.bg0, borderRadius: 6, fontSize: 9.5, fontFamily: F.mono, color: K.dim, lineHeight: 1.5 }}>
                {calc.basisState === "CONTANGO"
                  ? "선물 > 현물: 콘탱고 (정상). 보유비용 반영. 만기 수렴 시 선물 하방압력."
                  : calc.basisState === "BACKWARDATION"
                    ? "선물 < 현물: 백워데이션. 시장 스트레스 시그널. 차익 매수세(프로그램) 유입 가능."
                    : "현물 ≈ 선물: Fair Value 근처. 차익거래 유인 미미."}
              </div>
            </div>

            {/* Formula Quick Ref */}
            <div style={boxBase}>
              <Sec icon="📖" title="Formula Reference" tag="QUICK REF" tagC={K.dim} />
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", gap: 10 }}>
                {[
                  { t: "Z-Score", f: "Z = (Price − MA) / σ", d: "±2σ → 95.4% 신뢰구간 이탈" },
                  { t: "Expected Value", f: "EV = P(W)·W − P(L)·L − Cost", d: "양수일 때만 진입" },
                  { t: "Kelly Criterion", f: "f* = (b·p − q) / b", d: "Half-Kelly 실전 권장" },
                  { t: "ATR Stop", f: "SL = Entry ± ATR × mult", d: "동적 변동성 손절" },
                ].map((r, i) => (
                  <div key={i} style={{ padding: "10px 12px", background: K.bg0, borderRadius: 6 }}>
                    <div style={{ fontSize: 10, fontWeight: 700, color: K.acc, fontFamily: F.mono, marginBottom: 3 }}>{r.t}</div>
                    <div style={{ fontSize: 11, color: K.txt, fontFamily: F.mono, marginBottom: 2 }}>{r.f}</div>
                    <div style={{ fontSize: 9, color: K.dim }}>{r.d}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* FOOTER */}
      <div style={{ borderTop: `1px solid ${K.brd}`, padding: "12px 18px", textAlign: "center" }}>
        <span style={{ fontSize: 9, color: K.mut, fontFamily: F.mono }}>
          ⚠ 매매 보조 도구이며 투자 권유가 아닙니다. 모든 매매 결정의 책임은 본인에게 있습니다.
        </span>
      </div>
    </div>
  );
}
