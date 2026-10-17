import { test } from 'node:test';
import assert from 'node:assert/strict';
// @ts-expect-error TS5097: Node strip-types requires explicit extension.
import { qualifiedHistoricalMetrics, verifiedPortfolioHistory, type PortfolioSnapshotPoint } from '../lib/portfolio-history.ts';
const row=(day:string,overrides:Partial<PortfolioSnapshotPoint>={}):PortfolioSnapshotPoint=>({
 snapshot_date:`2026-10-${day}`,base_currency:'EUR',total_value_base:10000 * Math.pow(1.01, Number(day)-1),net_external_flow_base:0,pricing_coverage:1,daily_return:0.01,cumulative_twr:Math.pow(1.01,Number(day))-1,...overrides,
});
test('real complete return-qualified series is wired, sorted and never backfilled',()=>{
 const result=verifiedPortfolioHistory([row('02'),row('01')],'EUR');
 assert.deepEqual(result?.dates,['2026-10-01','2026-10-02']);assert.deepEqual(result?.nav,[10000,10100]);
});
test('live observed failure shape: many saved snapshots, no valid returns = no chart',()=>{
 assert.equal(verifiedPortfolioHistory([row('01',{daily_return:null,cumulative_twr:null}),row('02',{total_value_base:13640636,daily_return:null,cumulative_twr:null}),row('03',{pricing_coverage:0,total_value_base:0})],'EUR'),undefined);
});
test('does not bridge a gap, mix currencies, invent zero or show a single point as a series',()=>{
 for(const bad of [{daily_return:null},{cumulative_twr:null},{pricing_coverage:0.8},{total_value_base:NaN},{total_value_base:0},{base_currency:'USD'}]){
  assert.equal(verifiedPortfolioHistory([row('01'),row('02',bad),row('03')],'EUR'),undefined);
 }
});
test('a new valid suffix can appear without modifying the invalid past',()=>{
 const r=verifiedPortfolioHistory([row('01',{pricing_coverage:0}),row('02'),row('03')],'EUR');
 assert.deepEqual(r?.dates,['2026-10-02','2026-10-03']);
});
test('duplicate calendar day fails closed instead of a fabricated double session',()=>{
 assert.equal(verifiedPortfolioHistory([row('01'),row('01')],'EUR'),undefined);
});

test('rejects internally inconsistent NAV/flow/return or cumulative TWR even if coverage says 100%',()=>{
 assert.equal(verifiedPortfolioHistory([row('01'),row('02',{total_value_base:15000000})],'EUR'),undefined);
 assert.equal(verifiedPortfolioHistory([row('01'),row('02',{cumulative_twr:.99})],'EUR'),undefined);
 assert.equal(verifiedPortfolioHistory([row('01'),row('02',{net_external_flow_base:NaN})],'EUR'),undefined);
});

test('metrics cannot bridge incomplete history or use a stale/different period',()=>{
 const rows=[row('01'),row('02')], history=verifiedPortfolioHistory(rows,'EUR');
 const metrics={n_observations:2,cumulative_return:1.01**2-1};
 assert.equal(qualifiedHistoricalMetrics(rows,history,metrics),metrics);
 assert.equal(qualifiedHistoricalMetrics(rows,undefined,metrics),null);
 assert.equal(qualifiedHistoricalMetrics(rows,history,{...metrics,n_observations:25}),null);
 assert.equal(qualifiedHistoricalMetrics(rows,history,{...metrics,cumulative_return:0.4}),null);
 assert.equal(qualifiedHistoricalMetrics([row('00'),...rows],history,metrics),null);
 assert.equal(qualifiedHistoricalMetrics(rows,history,{...metrics,cumulative_return:NaN}),null);
});
