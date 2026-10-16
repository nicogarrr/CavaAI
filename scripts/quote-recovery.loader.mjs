import { resolve as contractResolve, load as contractLoad } from './research-client-contract.loader.mjs';
export async function resolve(specifier, context, nextResolve) {
  if (['@/lib/e2e-market-fixture', '@/lib/e2e-extended-quote-fixture', '@/lib/market/quote-symbol'].includes(specifier)) {
    return {url: new URL(`../${specifier.slice(2)}.ts`, import.meta.url).href, shortCircuit:true};
  }
  return contractResolve(specifier, context, nextResolve);
}
export const load = contractLoad;
