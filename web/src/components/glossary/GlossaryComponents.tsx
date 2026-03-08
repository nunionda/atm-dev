/**
 * Glossary Components — Tooltip, Term, InfoCard
 * 초보 트레이더를 위한 용어 설명 UI 컴포넌트
 */
import { useState } from 'react';
import { GLOSSARY, INFO_CARDS } from './glossaryData';
import './GlossaryComponents.css';

// ── Tooltip ────────────────────────────────────────────────────────

interface TooltipProps {
  text: string;
  formula?: string;
  tip?: string;
  position?: 'top' | 'bottom';
  children: React.ReactNode;
}

export function Tooltip({ text, formula, tip, position = 'top', children }: TooltipProps) {
  return (
    <span className="glossary-tooltip-wrap">
      {children}
      <span className={`glossary-tooltip-content ${position}`}>
        {text}
        {formula && <div className="glossary-tooltip-formula">{formula}</div>}
        {tip && <div className="glossary-tooltip-tip">{tip}</div>}
      </span>
    </span>
  );
}

// ── Term ───────────────────────────────────────────────────────────

interface TermProps {
  id: string;
  children?: React.ReactNode;
  position?: 'top' | 'bottom';
}

/**
 * 용어 래퍼. children이 없으면 "풀네임 (약어)" 자동 생성.
 * <Term id="atr" />  →  "평균 실질 변동폭 (ATR)"  + 호버 시 Tooltip
 * <Term id="atr">ATR</Term>  →  "ATR" 에 점선 밑줄 + 호버 시 Tooltip
 */
export function Term({ id, children, position = 'top' }: TermProps) {
  const entry = GLOSSARY[id];
  if (!entry) return <>{children || id}</>;

  const label = children || `${entry.fullKR} (${entry.abbr})`;

  return (
    <Tooltip
      text={entry.definition}
      formula={entry.formula}
      tip={entry.tip}
      position={position}
    >
      <span className="glossary-term">{label}</span>
    </Tooltip>
  );
}

// ── InfoCard ───────────────────────────────────────────────────────

interface InfoCardProps {
  id: string;
}

/**
 * ⓘ 버튼 + 클릭 시 인라인 확장 설명 패널.
 * Sec 컴포넌트의 infoId prop과 함께 사용.
 */
export function InfoCard({ id }: InfoCardProps) {
  const [open, setOpen] = useState(false);
  const card = INFO_CARDS[id];
  if (!card) return null;

  return (
    <>
      <button
        className={`glossary-info-btn ${open ? 'active' : ''}`}
        onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
        title={`${card.titleKR} 설명 보기`}
      >
        i
      </button>
      <div className={`glossary-info-panel ${open ? 'open' : ''}`}>
        <div className="glossary-info-panel-header">
          <span className="glossary-info-panel-title">
            <span className="icon">{card.icon}</span>
            {card.titleKR} ({card.titleEN})
          </span>
          <button className="glossary-info-panel-close" onClick={() => setOpen(false)}>×</button>
        </div>
        <div className="glossary-info-panel-body">{card.body}</div>
        {card.tip && (
          <div className="glossary-info-panel-tip">💡 {card.tip}</div>
        )}
      </div>
    </>
  );
}
