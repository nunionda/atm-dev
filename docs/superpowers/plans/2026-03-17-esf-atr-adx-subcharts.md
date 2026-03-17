# ESF ATR & ADX Subcharts Integration Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan.

**Goal:** ATR(14)와 ADX/DMI 인디케이터를 메인 lightweight-charts 차트의 서브차트로 통합한다.

**Architecture:** `ESFIntradayChart.tsx`의 `SubchartState` 타입에 `atr`·`adx` 불리언을 추가하고, 기존 RSI/MACD/Z-Score 서브차트 패턴을 그대로 따라 두 개의 시계열 서브차트를 삽입한다. `ESFuturesScalping.tsx`에서 기본값을 `atr: true, adx: true`로 활성화한다.

**Tech Stack:** lightweight-charts, React, TypeScript

---

### Task 1: SubchartState 타입 확장 + ref 추가

**Files:**
- Modify: `web/src/components/esf/ESFIntradayChart.tsx`

- [ ] `SubchartState` 인터페이스에 `atr: boolean`·`adx: boolean` 추가
- [ ] `useRef<HTMLDivElement>(null)` 두 개 (`atrRef`, `adxRef`) 추가
- [ ] `buildChart` 함수 파라미터 destructuring에서 default 값도 업데이트 (`atr: true, adx: true`)

### Task 2: ATR 서브차트 추가

**Files:**
- Modify: `web/src/components/esf/ESFIntradayChart.tsx` — 기존 Z-Score 서브차트 블록 뒤에 삽입

ATR 서브차트 구성:
- 높이 100px
- `atr_14` 라인 (color: `#f59e0b`, width 2) — 주 지표
- 20봉 롤링 평균 라인 (color: `rgba(255,255,255,0.25)`, width 1, dashed) — 기준선
- 레이블: `ATR(14)` watermark

평균 계산:
```typescript
// 20봉 롤링 평균 (candle 루프 내에서)
const atrValues = candles.filter(c => c.atr_14 != null).map(c => c.atr_14!);
const atrAvgData = dedupByTime(
  candles
    .filter((c) => c.atr_14 != null)
    .map((c, idx, arr) => {
      const window = arr.slice(Math.max(0, idx - 19), idx + 1).filter(x => x.atr_14 != null);
      const avg = window.reduce((s, x) => s + x.atr_14!, 0) / window.length;
      return { time: parseTime(c.datetime), value: avg };
    })
);
```

### Task 3: ADX 서브차트 추가

**Files:**
- Modify: `web/src/components/esf/ESFIntradayChart.tsx` — ATR 서브차트 블록 뒤에 삽입

ADX 서브차트 구성:
- 높이 100px
- ADX 라인: color `#e0e0e0`, width 2 — 추세 강도
- +DI 라인: color `#22c55e`, width 1.5 — 매수 압력
- -DI 라인: color `#ef4444`, width 1.5 — 매도 압력
- 기준선 3개: 20 (약세, gray), 25 (추세 시작, blue), 40 (강한 추세, orange)

```typescript
if (subcharts.adx && adxRef.current) {
  const adxChart = createChart(adxRef.current, {
    ...SUBCHART_OPTIONS,
    width: adxRef.current.clientWidth,
    height: 100,
  });
  subchartList.push(adxChart);

  const adxLine = adxChart.addLineSeries({ color: '#e0e0e0', lineWidth: 2 });
  const plusDiLine = adxChart.addLineSeries({ color: '#22c55e', lineWidth: 1.5 });
  const minusDiLine = adxChart.addLineSeries({ color: '#ef4444', lineWidth: 1.5 });

  // Reference levels
  adxLine.createPriceLine({ price: 40, color: 'rgba(245, 158, 11, 0.4)', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'Strong' });
  adxLine.createPriceLine({ price: 25, color: 'rgba(59, 130, 246, 0.4)', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'Trend' });
  adxLine.createPriceLine({ price: 20, color: 'rgba(255, 255, 255, 0.15)', lineWidth: 1, lineStyle: 3, axisLabelVisible: false, title: '' });

  const adxData = dedupByTime(candles.filter(c => c.adx != null).map(c => ({ time: parseTime(c.datetime), value: c.adx! })));
  const plusDiData = dedupByTime(candles.filter(c => c.plus_di != null).map(c => ({ time: parseTime(c.datetime), value: c.plus_di! })));
  const minusDiData = dedupByTime(candles.filter(c => c.minus_di != null).map(c => ({ time: parseTime(c.datetime), value: c.minus_di! })));

  adxLine.setData(adxData);
  plusDiLine.setData(plusDiData);
  minusDiLine.setData(minusDiData);
}
```

### Task 4: JSX 반환 + resize + sync 업데이트

**Files:**
- Modify: `web/src/components/esf/ESFIntradayChart.tsx`

- [ ] `return` JSX에 div 두 개 추가:
  ```tsx
  {subcharts.atr && <div ref={atrRef} className="esf-subchart-container" />}
  {subcharts.adx && <div ref={adxRef} className="esf-subchart-container" />}
  ```
- [ ] `handleResize` 내부: `subchartList.forEach` 이미 모든 서브차트를 처리하므로 추가 수정 불필요
- [ ] `buildChart` 의존성 배열에 변경 없음 (`subcharts` 객체 전체 포함)
- [ ] `cleanup` 반환: `subchartList.forEach(c => c.remove())` 이미 처리

### Task 5: ESFuturesScalping.tsx 호출부 업데이트

**Files:**
- Modify: `web/src/pages/ESFuturesScalping.tsx`

현재 `<ESFIntradayChart>` 사용 위치에서 `subcharts` prop을 업데이트:
```tsx
// 찾기:
subcharts={{ rsi: true, macd: true, zscore: false }}
// 또는 기본값 사용 중인 경우

// 변경:
subcharts={{ rsi: true, macd: true, zscore: false, atr: true, adx: true }}
```

### Task 6: TypeScript 검증

- [ ] `cd web && npx tsc --noEmit`
- [ ] 에러 없으면 완료
