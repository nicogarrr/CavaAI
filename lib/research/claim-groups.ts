/** Do not merge claims across thesis versions or assign unknown ids a version. */
export function groupClaimsByVersion<T extends { thesis_version_id: number | null }>(
  claims: T[], versions: Array<{ id: number; version: number }>,
): Array<{ key: string; label: string; claims: T[] }> {
  const numbers = new Map(versions.map(version => [version.id, version.version]));
  const groups = new Map<string, { key: string; label: string; claims: T[] }>();
  for (const claim of claims) {
    const id = claim.thesis_version_id;
    const key = id == null ? 'manual' : `thesis-${id}`;
    const version = id == null ? null : numbers.get(id);
    const label = id == null ? 'Sin versión de tesis vinculada'
      : version == null ? `Tesis vinculada (ID ${id}, versión N/D)` : `Tesis v${version}`;
    if (!groups.has(key)) groups.set(key, { key, label, claims: [] });
    groups.get(key)!.claims.push(claim);
  }
  return [...groups.values()];
}
