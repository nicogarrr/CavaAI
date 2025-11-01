"use client";

import React, { useMemo } from "react";

type Position = PortfolioPositionWithData;

type AllocationSlice = {
  label: string;
  value: number;
  color: string;
};

function generatePalette(count: number): string[] {
  // Paleta accesible y consistente
  const base = [
    "#0FEDBE",
    "#2962FF",
    "#FFB020",
    "#FF5A5F",
    "#8E5CF6",
    "#00B8D9",
    "#34D399",
    "#F59E0B",
    "#EC4899",
    "#60A5FA",
  ];
  const out: string[] = [];
  for (let i = 0; i < count; i++) out.push(base[i % base.length]);
  return out;
}

function toConicGradient(slices: AllocationSlice[]): string {
  const total = slices.reduce((s, x) => s + x.value, 0) || 1;
  let acc = 0;
  const parts: string[] = [];
  for (const s of slices) {
    const start = (acc / total) * 360;
    acc += s.value;
    const end = (acc / total) * 360;
    parts.push(`${s.color} ${start}deg ${end}deg`);
  }
  return `conic-gradient(${parts.join(", ")})`;
}

function classifySymbol(symbol: string): "ETF" | "CRYPTO" | "COMMODITY" | "STOCK" {
  const s = symbol.toUpperCase();
  const etfs = new Set([
    "URTH",
    "VWO",
    "VSS",
    "SPY",
    "VOO",
    "QQQ",
    "VT",
    "ACWI",
    "EEM",
    "BITO",
  ]);
  const commodity = new Set(["GLD", "SLV", "IAU"]);
  if (etfs.has(s)) return "ETF";
  if (commodity.has(s)) return "COMMODITY";
  if (s.includes("BTC") || s === "COIN") return "CRYPTO";
  return "STOCK";
}

function buildSlicesBySymbol(positions: Position[]): AllocationSlice[] {
  const palette = generatePalette(positions.length);
  const slices: AllocationSlice[] = positions
    .filter((p) => (p.currentValue ?? 0) > 0 || (p.invested ?? 0) > 0)
    .map((p, idx) => ({
      label: p.symbol,
      value: Math.max(p.currentValue ?? 0, 0),
      color: palette[idx],
    }));
  return slices;
}

function buildSlicesByCategory(positions: Position[]): AllocationSlice[] {
  const map = new Map<string, number>();
  for (const p of positions) {
    const key = classifySymbol(p.symbol);
    const val = Math.max(p.currentValue ?? 0, 0);
    map.set(key, (map.get(key) || 0) + val);
  }
  const entries = Array.from(map.entries());
  const palette = generatePalette(entries.length);
  return entries.map(([label, value], i) => ({ label, value, color: palette[i] }));
}

function Donut({ slices, size = 220, thickness = 28 }: { slices: AllocationSlice[]; size?: number; thickness?: number }) {
  const gradient = useMemo(() => toConicGradient(slices), [slices]);
  const total = slices.reduce((s, x) => s + x.value, 0);
  return (
    <div className="flex flex-col items-center gap-4">
      <div
        className="rounded-full relative"
        style={{ width: size, height: size, backgroundImage: gradient }}
      >
        <div
          className="absolute inset-0 m-auto rounded-full bg-[#0F0F0F]"
          style={{ width: size - thickness * 2, height: size - thickness * 2 }}
        />
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-sm text-gray-300">${total.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
        </div>
      </div>
      <ul className="grid grid-cols-2 gap-2 w-full">
        {slices.map((s) => (
          <li key={s.label} className="flex items-center gap-2 text-sm text-gray-300">
            <span className="inline-block w-3 h-3 rounded" style={{ backgroundColor: s.color }} />
            <span className="truncate">{s.label}</span>
            <span className="ml-auto tabular-nums">{((s.value / (total || 1)) * 100).toFixed(1)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function PortfolioAllocation({ positions }: { positions: Position[] }) {
  const bySymbol = useMemo(() => buildSlicesBySymbol(positions), [positions]);
  const byCategory = useMemo(() => buildSlicesByCategory(positions), [positions]);

  return (
    <section className="w-full bg-[#0F0F0F] rounded-lg border border-gray-800 p-6">
      <h2 className="text-2xl font-semibold mb-4">Diversificación</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <div>
          <h3 className="text-sm text-gray-400 mb-3">Por categoría</h3>
          <Donut slices={byCategory} />
        </div>
        <div>
          <h3 className="text-sm text-gray-400 mb-3">Por símbolo</h3>
          <Donut slices={bySymbol} />
        </div>
      </div>
    </section>
  );
}
